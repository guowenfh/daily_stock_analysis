"""Extractor dispatch by display_type."""
import json
import logging

from sqlalchemy.orm import Session

from src.signal.models import Content, SignalMention
from src.signal.extractor.base import BaseExtractor, MentionData, ExtractResult

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    def __init__(self, session: Session, extractors: dict[str, BaseExtractor]):
        self.session = session
        self.extractors = extractors

    def extract_all(self, contents: list[Content] = None, limit: int = 20) -> ExtractResult:
        result = ExtractResult()

        if contents is None:
            contents = (
                self.session.query(Content)
                .filter(Content.status == "pending_extract")
                .limit(limit)
                .all()
            )

        for content in contents:
            extractor = self.extractors.get(content.display_type)
            if not extractor:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = f"No extractor for display_type={content.display_type}"
                result.failed += 1
                continue

            try:
                mentions = extractor.extract(content)
                if not mentions:
                    content.status = "extracted"
                    result.extracted += 1
                    continue

                for m_data in mentions:
                    mention = SignalMention(
                        content_id=content.id,
                        creator_id=content.creator_id,
                        asset_name=m_data.name,
                        asset_code=m_data.code,
                        asset_type=m_data.asset_type,
                        market=m_data.market,
                        sentiment=m_data.sentiment,
                        confidence=m_data.confidence,
                        is_primary=m_data.is_primary,
                        reasoning=m_data.reasoning,
                        trade_advice=m_data.trade_advice,
                        key_levels_json=json.dumps(m_data.key_levels or {}, ensure_ascii=False),
                    )
                    mention.set_quality_flags(m_data.quality_flags)
                    self.session.add(mention)

                content.status = "extracted"
                result.extracted += 1

            except Exception as e:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = str(e)[:500]
                result.failed += 1
                result.errors.append(f"Content {content.id}: {e}")
                logger.exception("Extraction failed for content %d", content.id)

        self.session.commit()
        return result
