"""Base extractor interface and shared types."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MentionData:
    name: str
    code: Optional[str] = None
    asset_type: str = "stock"
    market: str = "unknown"
    sentiment: str = "neutral"
    confidence: float = 0.5
    is_primary: bool = False
    reasoning: Optional[str] = None
    trade_advice: Optional[str] = None
    key_levels: Optional[dict] = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    extracted: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, content) -> list[MentionData]:
        """Extract signal mentions from content. Returns list of MentionData."""
        ...

    def _apply_quality_rules(self, mentions: list[MentionData], content) -> list[MentionData]:
        for m in mentions:
            if not m.code:
                if "code_unresolved" not in m.quality_flags:
                    m.quality_flags.append("code_unresolved")
            if not m.trade_advice:
                if "no_trade_advice" not in m.quality_flags:
                    m.quality_flags.append("no_trade_advice")
            if m.confidence < 0.4:
                if "low_llm_confidence" not in m.quality_flags:
                    m.quality_flags.append("low_llm_confidence")
        return mentions
