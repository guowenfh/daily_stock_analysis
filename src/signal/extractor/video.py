"""Video subtitle signal extractor."""
import json
import logging
import re
from typing import Optional

from src.signal.extractor.base import BaseExtractor, MentionData

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20


MAX_TRANSCRIPT_CHARS = 6000


class VideoSignalExtractor(BaseExtractor):
    def __init__(self, litellm_model: str, temperature: float = 0.3, max_tokens: int = 8192, timeout: int = 300):
        self.model = litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def extract(self, content) -> list[MentionData]:
        transcript_text, quality = self._get_best_transcript(content)
        title = content.title or ""

        if transcript_text:
            if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
                transcript_text = transcript_text[:MAX_TRANSCRIPT_CHARS]
            full_text = f"标题: {title}\n\n字幕内容:\n{transcript_text}"
        else:
            full_text = title

        if len(full_text.strip()) < MIN_TEXT_LENGTH:
            return []

        title_only = not transcript_text

        from src.signal.prompt_manager import PromptManager

        system_prompt = PromptManager.get_prompt("video")
        if not system_prompt:
            system_prompt = PromptManager.get_prompt("text")
        if not system_prompt:
            return []

        try:
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_text},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            raw = response.choices[0].message.content
            data = self._parse_json(raw)
            mentions = self._to_mention_data(data)

            for m in mentions:
                if title_only:
                    m.confidence = min(m.confidence, 0.4)
                    if "title_only" not in m.quality_flags:
                        m.quality_flags.append("title_only")
                if quality == "short":
                    if "subtitle_missing" not in m.quality_flags:
                        m.quality_flags.append("subtitle_missing")

            return self._apply_quality_rules(mentions, content)

        except Exception as e:
            logger.exception("Video extraction failed: %s", e)
            return []

    def _get_best_transcript(self, content) -> tuple[Optional[str], Optional[str]]:
        transcripts = getattr(content, "transcripts", None) or []
        if not transcripts:
            return None, None

        priority = {"good": 0, "short": 1, "title_only": 2, "failed": 3}
        sorted_t = sorted(transcripts, key=lambda t: priority.get(t.quality, 99))

        best = sorted_t[0] if sorted_t else None
        if best and best.quality != "failed":
            return best.text, best.quality
        return None, None

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        return json.loads(raw)

    def _to_mention_data(self, data: dict) -> list[MentionData]:
        mentions_raw = data.get("mentions", [])
        result = []
        for m in mentions_raw:
            if not m.get("name"):
                continue
            result.append(MentionData(
                name=m["name"],
                code=m.get("code") or None,
                asset_type=m.get("asset_type", "stock"),
                market=m.get("market", "unknown"),
                sentiment=m.get("sentiment", "neutral"),
                confidence=float(m.get("confidence", 0.5)),
                is_primary=bool(m.get("is_primary", False)),
                reasoning=m.get("reasoning"),
                trade_advice=m.get("trade_advice") or None,
                key_levels=m.get("key_levels"),
            ))
        return result
