"""Content enrichment: subtitle extraction and OCR."""
import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Optional

import yaml
from sqlalchemy.orm import Session

from src.signal.models import Content, ContentTranscript

logger = logging.getLogger(__name__)

WHISPER_TIMEOUT = 300
MIN_SUBTITLE_LENGTH = 50

_whisper_lock = threading.Lock()

_BVID_RE = re.compile(r"BV[\w]+")


@dataclass
class EnrichResult:
    enriched: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ContentEnricher:
    def __init__(self, session: Session):
        self.session = session

    def enrich_batch(self, limit: int = 20) -> EnrichResult:
        result = EnrichResult()

        contents = (
            self.session.query(Content)
            .filter(Content.status == "pending_enrich")
            .limit(limit)
            .all()
        )

        for content in contents:
            try:
                if content.display_type == "video_subtitle":
                    self._enrich_video(content, result)
                elif content.display_type == "image_text":
                    self._enrich_image(content, result)
                else:
                    content.status = "pending_extract"
                    result.skipped += 1
            except Exception as e:
                content.status = "failed"
                content.failure_stage = "enrich"
                content.failure_reason = str(e)[:500]
                result.failed += 1
                result.errors.append(f"Content {content.id}: {e}")
                logger.exception("Enrichment failed for content %d", content.id)

        self.session.commit()
        return result

    @staticmethod
    def _extract_bvid(content: Content) -> Optional[str]:
        pid = content.platform_content_id or ""
        if pid.startswith("BV"):
            return pid
        for field in (content.url, pid):
            if field:
                m = _BVID_RE.search(field)
                if m:
                    return m.group(0)
        return None

    def _enrich_video(self, content: Content, result: EnrichResult):
        bvid = self._extract_bvid(content)
        if not bvid:
            content.status = "pending_extract"
            result.skipped += 1
            return

        subtitle_text = self._get_platform_subtitle(bvid)

        if not subtitle_text:
            subtitle_text = self._get_whisper_transcript(bvid)

        if subtitle_text:
            quality = "good" if len(subtitle_text) >= MIN_SUBTITLE_LENGTH else "short"
            transcript = ContentTranscript(
                content_id=content.id,
                source=(
                    "platform"
                    if len(subtitle_text) >= MIN_SUBTITLE_LENGTH
                    else "whisper"
                ),
                text=subtitle_text,
                quality=quality,
            )
            self.session.add(transcript)
            content.status = "pending_extract"
            result.enriched += 1
        else:
            transcript = ContentTranscript(
                content_id=content.id,
                source="platform",
                text=content.title or "",
                quality="title_only",
            )
            self.session.add(transcript)
            content.status = "pending_extract"
            result.enriched += 1

    def _get_platform_subtitle(self, bvid: str) -> Optional[str]:
        try:
            proc = subprocess.run(
                ["bili", "video", bvid, "--subtitle", "--yaml"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.debug("Platform subtitle timed out for %s", bvid)
            return None

        try:
            if proc.returncode != 0:
                return None
            data = yaml.safe_load(proc.stdout)
            if isinstance(data, dict):
                inner = data.get("data", data)
                if isinstance(inner, dict):
                    sub = inner.get("subtitle", {})
                    if isinstance(sub, dict):
                        text = sub.get("text", "")
                        if text:
                            return text
                return data.get("subtitle", "") or data.get("text", "")
            if isinstance(data, str):
                return data
            return None
        except Exception as e:
            logger.debug("Platform subtitle parse failed for %s: %s", bvid, e)
            return None

    def _get_whisper_transcript(self, bvid: str) -> Optional[str]:
        logger.debug("Whisper lock acquiring for %s", bvid)
        _whisper_lock.acquire()
        logger.debug("Whisper lock acquired for %s", bvid)

        tmp_dir = tempfile.mkdtemp(prefix=f"signal_audio_{bvid}_")
        try:
            audio_proc = subprocess.run(
                ["bili", "audio", bvid, "--no-split", "-o", tmp_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if audio_proc.returncode != 0:
                return None

            m4a_files = [
                os.path.join(tmp_dir, f)
                for f in os.listdir(tmp_dir)
                if f.endswith(".m4a")
            ]
            if not m4a_files:
                return None
            audio_path = m4a_files[0]

            whisper_proc = subprocess.run(
                [
                    "whisper",
                    "--model",
                    "turbo",
                    "--language",
                    "zh",
                    "--output_format",
                    "txt",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=WHISPER_TIMEOUT,
            )
            if whisper_proc.returncode != 0:
                return None

            return whisper_proc.stdout.strip() or None
        except subprocess.TimeoutExpired:
            logger.warning("Whisper timed out for %s", bvid)
            return None
        except Exception as e:
            logger.debug("Whisper failed for %s: %s", bvid, e)
            return None
        finally:
            _whisper_lock.release()

    def _enrich_image(self, content: Content, result: EnrichResult):
        # Multimodal model handles image recognition directly in extraction step.
        # No separate OCR enrichment needed — just pass through to extractor.
        content.status = "pending_extract"
        result.enriched += 1
