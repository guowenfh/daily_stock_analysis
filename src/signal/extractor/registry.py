"""Extractor dispatch by display_type."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from src.signal.models import Content, SignalMention
from src.signal.extractor.base import BaseExtractor, ExtractResult

if TYPE_CHECKING:
    from src.signal.asset_resolver import AssetResolver

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    def __init__(
        self,
        session: Session,
        extractors: dict[str, BaseExtractor],
        asset_resolver: Optional[AssetResolver] = None,
    ):
        self.session = session
        self.extractors = extractors
        self.asset_resolver = asset_resolver

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
            existing_count = (
                self.session.query(SignalMention)
                .filter_by(content_id=content.id)
                .count()
            )
            if existing_count > 0:
                content.status = "extracted"
                result.skipped += 1
                logger.info(
                    "Skipped content %d: %d mentions already exist",
                    content.id,
                    existing_count,
                )
                continue

            extractor = self.extractors.get(content.display_type)
            if not extractor:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = f"No extractor for display_type={content.display_type}"
                result.failed += 1
                continue

            try:
                mentions = extractor.extract(content)
                if self.asset_resolver:
                    mentions = self.asset_resolver.resolve(mentions)
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
