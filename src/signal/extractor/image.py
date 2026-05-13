"""Image content signal extractor."""
import base64
import json
import logging
import re
from typing import Optional

import requests

from src.signal.extractor.base import BaseExtractor, MentionData

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20
MAX_IMAGES = 5
IMAGE_DOWNLOAD_TIMEOUT = 30


def _url_to_base64(url: str) -> Optional[str]:
    """Download image and return data URI (base64 encoded)."""
    try:
        resp = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/png")
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{content_type};base64,{b64}"
    except Exception as e:
        logger.debug("Failed to download image %s: %s", url[:80], e)
        return None


class ImageSignalExtractor(BaseExtractor):
    def __init__(self, litellm_model: str, temperature: float = 0.3, max_tokens: int = 8192, timeout: int = 300):
        self.model = litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def extract(self, content) -> list[MentionData]:
        text = content.text or ""
        title = content.title or ""
        full_text = f"{title}\n{text}".strip()

        image_urls = self._get_image_urls(content)

        if len(full_text) < MIN_TEXT_LENGTH and not image_urls:
            return []

        from src.signal.prompt_manager import PromptManager

        system_prompt = PromptManager.get_prompt("image")
        if not system_prompt:
            system_prompt = PromptManager.get_prompt("text")
        if not system_prompt:
            return []

        try:
            from src.signal.rate_limiter import rate_limited_completion

            messages = [{"role": "system", "content": system_prompt}]

            if image_urls:
                user_content = [{"type": "text", "text": full_text}]
                for url in image_urls[:MAX_IMAGES]:
                    data_uri = _url_to_base64(url)
                    if data_uri:
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        })
                has_images = len(user_content) > 1
                messages.append({"role": "user", "content": user_content})
            else:
                messages.append({"role": "user", "content": full_text})

            response = rate_limited_completion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            raw = response.choices[0].message.content
            data = self._parse_json(raw)
            mentions = self._to_mention_data(data)
            return self._apply_quality_rules(mentions, content)

        except Exception as e:
            logger.exception("Image extraction failed: %s", e)
            if image_urls and full_text:
                return self._fallback_text_only(full_text, system_prompt, content)
            return []

    def _get_image_urls(self, content) -> list[str]:
        media_list = getattr(content, "media", None) or []
        urls = []
        for m in media_list:
            if m.media_type == "image" and m.url:
                urls.append(m.url)
        return urls

    def _fallback_text_only(self, text: str, system_prompt: str, content) -> list[MentionData]:
        try:
            from src.signal.rate_limiter import rate_limited_completion

            response = rate_limited_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            raw = response.choices[0].message.content
            data = self._parse_json(raw)
            mentions = self._to_mention_data(data)
            for m in mentions:
                if "image_ocr_incomplete" not in m.quality_flags:
                    m.quality_flags.append("image_ocr_incomplete")
            return self._apply_quality_rules(mentions, content)
        except Exception:
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
