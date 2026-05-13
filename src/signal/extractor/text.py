"""Text content signal extractor."""
import json
import logging
import re

from src.signal.extractor.base import BaseExtractor, MentionData

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20


class TextSignalExtractor(BaseExtractor):
    def __init__(self, litellm_model: str, temperature: float = 0.3, max_tokens: int = 8192, timeout: int = 300):
        self.model = litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def extract(self, content) -> list[MentionData]:
        text = content.text or ""
        title = content.title or ""
        full_text = f"{title}\n{text}".strip()

        if len(full_text) < MIN_TEXT_LENGTH:
            logger.debug("Text too short (%d chars), skipping", len(full_text))
            return []

        from src.signal.prompt_manager import PromptManager

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
            return self._apply_quality_rules(mentions, content)

        except Exception as e:
            logger.exception("LLM extraction failed: %s", e)
            return []

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
