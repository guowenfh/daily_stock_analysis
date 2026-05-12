"""Content enrichment: subtitle extraction and OCR."""
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional

import yaml
from sqlalchemy.orm import Session

from src.signal.models import Content, ContentMedia, ContentTranscript

logger = logging.getLogger(__name__)

WHISPER_TIMEOUT = 300
MIN_SUBTITLE_LENGTH = 50

_whisper_lock = threading.Lock()


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

    def _enrich_video(self, content: Content, result: EnrichResult):
        bvid = content.platform_content_id
        if not bvid or not bvid.startswith("BV"):
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
                return data.get("subtitle", "") or data.get("text", "")
            if isinstance(data, str):
                return data
            return None
        except Exception as e:
            logger.debug("Platform subtitle parse failed for %s: %s", bvid, e)
            return None

    def _get_whisper_transcript(self, bvid: str) -> Optional[str]:
        if not _whisper_lock.acquire(timeout=0):
            logger.info("Whisper lock busy, skipping %s", bvid)
            return None

        try:
            audio_proc = subprocess.run(
                ["bili", "audio", bvid],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if audio_proc.returncode != 0:
                return None

            audio_path = audio_proc.stdout.strip()
            if not audio_path:
                return None

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
        media_list = (
            self.session.query(ContentMedia)
            .filter(
                ContentMedia.content_id == content.id,
                ContentMedia.media_type == "image",
            )
            .all()
        )

        if not media_list:
            content.status = "pending_extract"
            result.skipped += 1
            return

        try:
            import litellm
            from src.config import get_config

            config = get_config()

            for media in media_list:
                if not media.url:
                    continue
                try:
                    response = litellm.completion(
                        model=config.litellm_model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "提取图片中的所有文字内容，保持原始格式。"
                                    "如果是K线图或行情截图，描述关键信息。"
                                ),
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": media.url},
                                    },
                                ],
                            },
                        ],
                        max_tokens=2048,
                    )
                    ocr_text = response.choices[0].message.content
                    media.ocr_text = ocr_text
                except Exception as e:
                    logger.debug("OCR failed for media %d: %s", media.id, e)

            content.status = "pending_extract"
            result.enriched += 1

        except Exception as e:
            content.status = "failed"
            content.failure_stage = "enrich"
            content.failure_reason = f"Image OCR failed: {e}"
            result.failed += 1
            result.errors.append(f"Content {content.id} image OCR: {e}")
