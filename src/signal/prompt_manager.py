"""Load and render YAML prompt templates."""
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"


class PromptManager:
    _cache: dict[str, dict] = {}

    @classmethod
    def get_prompt(cls, display_type: str) -> Optional[str]:
        filename = f"signal_{display_type}.yaml"
        if filename not in cls._cache:
            path = PROMPTS_DIR / filename
            if not path.exists():
                logger.warning("Prompt file not found: %s", path)
                return None
            with open(path, "r", encoding="utf-8") as f:
                cls._cache[filename] = yaml.safe_load(f)

        data = cls._cache.get(filename, {})
        return data.get("system_prompt", "")

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
