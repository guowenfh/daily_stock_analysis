"""Content enrichment: subtitle extraction and OCR."""
import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import yaml
from sqlalchemy.orm import Session

from src.signal.models import Content, ContentTranscript

logger = logging.getLogger(__name__)

WHISPER_TIMEOUT = 300
MIN_SUBTITLE_LENGTH = 50

_whisper_lock = threading.Lock()

_BVID_RE = re.compile(r"BV[\w]+")


class SubtitleFetchError(Exception):
    """Raised when subtitle fetch fails but subtitles may exist."""


@dataclass
class EnrichResult:
    enriched: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ContentEnricher:
    def __init__(self, session: Session):
        self.session = session

    def enrich_batch(
        self,
        limit: int = 20,
        on_progress: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> EnrichResult:
        result = EnrichResult()

        contents = (
            self.session.query(Content)
            .filter(Content.status == "pending_enrich")
            .limit(limit)
            .all()
        )
        total = len(contents)

        for processed, content in enumerate(contents, start=1):
            if cancel_check and cancel_check():
                break
            item_result = EnrichResult()
            try:
                if content.display_type == "video_subtitle":
                    self._enrich_video(content, item_result)
                elif content.display_type == "image_text":
                    self._enrich_image(content, item_result)
                else:
                    content.status = "pending_extract"
                    item_result.skipped += 1
                self.session.commit()
                result.enriched += item_result.enriched
                result.skipped += item_result.skipped
            except Exception as e:
                self.session.rollback()
                result.failed += 1
                result.errors.append(f"Content {content.id}: {e}")
                logger.exception("Enrichment failed for content %d", content.id)
                self._mark_failed(content.id, e)
            finally:
                if on_progress:
                    on_progress(processed, total)
        return result

    def _mark_failed(self, content_id: int, error: Exception):
        try:
            content = self.session.get(Content, content_id)
            if content is None:
                return
            content.status = "failed"
            content.failure_stage = "enrich"
            content.failure_reason = str(error)[:500]
            content.suggested_action = "review"
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Failed to mark content %d as failed", content_id)

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

        subtitle_text = None

        # Try platform subtitle first; raise on fetch failures so the
        # caller can mark the content as failed instead of silently
        # falling through to title-only.
        try:
            subtitle_text = self._get_platform_subtitle(bvid)
        except SubtitleFetchError:
            logger.warning("Platform subtitle fetch failed for %s", bvid)
            raise

        # Fallback to whisper only when platform reports no subtitle.
        if not subtitle_text:
            try:
                subtitle_text = self._get_whisper_transcript(bvid)
            except SubtitleFetchError:
                logger.warning("Whisper transcript fetch failed for %s", bvid)
                raise

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
            # No subtitle from either source — genuinely no transcript
            # available. Record title-only so extraction can still run
            # with reduced confidence.
            logger.info("No subtitle available for %s, using title-only", bvid)
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
        """Fetch platform subtitle for a video.

        Returns subtitle text when available, None when the video genuinely
        has no subtitle.  Raises SubtitleFetchError when the fetch command
        fails (timeout, non-zero exit, parse error) so callers can
        distinguish "no subtitle" from "fetch failed".
        """
        try:
            proc = subprocess.run(
                ["bili", "video", bvid, "--subtitle", "--yaml"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise SubtitleFetchError(f"Platform subtitle timed out for {bvid}")

        if proc.returncode != 0:
            raise SubtitleFetchError(
                f"Platform subtitle command failed for {bvid}: "
                f"exit={proc.returncode}, stderr={proc.stderr[:200]}"
            )

        try:
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
            raise SubtitleFetchError(
                f"Platform subtitle parse failed for {bvid}: {e}"
            )

    def _get_whisper_transcript(self, bvid: str) -> Optional[str]:
        """Fetch transcript via whisper.

        Returns transcript text when available, None when no audio or
        whisper produced no output.  Raises SubtitleFetchError on timeout
        (whisper couldn't process the audio).
        """
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
            raise SubtitleFetchError(f"Whisper timed out for {bvid}")
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
