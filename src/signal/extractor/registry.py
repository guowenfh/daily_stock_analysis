"""Extractor dispatch by display_type."""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import TYPE_CHECKING, Callable, Optional

from sqlalchemy.orm import Session

from src.signal.models import Content, SignalMention
from src.signal.extractor.base import BaseExtractor, ExtractResult, MentionData

if TYPE_CHECKING:
    from src.signal.asset_resolver import AssetResolver

logger = logging.getLogger(__name__)

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "2"))


def wait_first(futures: set[Future]) -> tuple[set[Future], set[Future]]:
    """Wait for at least one future to complete. Returns (done, not_done)."""
    done, not_done = wait(futures, return_when=FIRST_COMPLETED)
    return done, not_done


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

    def extract_all(
        self,
        contents: list[Content] = None,
        limit: int = 20,
        on_progress: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExtractResult:
        result = ExtractResult()

        if contents is None:
            contents = (
                self.session.query(Content)
                .filter(Content.status == "pending_extract")
                .limit(limit)
                .all()
            )

        total = len(contents)
        if total == 0:
            return result

        # Pre-load media to avoid lazy-load issues in threads
        for c in contents:
            _ = c.media

        # Filter out already-extracted and no-extractor items first
        work_items = []
        for content in contents:
            existing_count = (
                self.session.query(SignalMention)
                .filter_by(content_id=content.id)
                .count()
            )
            if existing_count > 0:
                content.status = "extracted"
                result.skipped += 1
                continue

            extractor = self.extractors.get(content.display_type)
            if not extractor:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = f"No extractor for display_type={content.display_type}"
                result.failed += 1
                continue

            work_items.append((content, extractor))

        processed = total - len(work_items)
        if on_progress:
            on_progress(processed, total)

        if not work_items:
            self.session.commit()
            return result

        def _do_extract(content: Content, extractor: BaseExtractor) -> tuple[Content, Optional[list[MentionData]], Optional[str]]:
            """Run extraction in worker thread (LLM I/O bound)."""
            try:
                mentions = extractor.extract(content)
                return content, mentions, None
            except Exception as e:
                return content, None, str(e)[:500]

        # Incremental submission: only MAX_WORKERS in-flight at a time
        # so cancellation takes effect quickly
        work_iter = iter(work_items)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            pending = set()
            cancelled = False

            # Seed the pool
            for _ in range(min(MAX_WORKERS, len(work_items))):
                content, extractor = next(work_iter)
                pending.add(pool.submit(_do_extract, content, extractor))

            while pending:
                done, pending = wait_first(pending)

                for future in done:
                    content, mentions, error = future.result()

                    if error:
                        content.status = "failed"
                        content.failure_stage = "extract"
                        content.failure_reason = error
                        result.failed += 1
                        result.errors.append(f"Content {content.id}: {error}")
                    else:
                        if self.asset_resolver and mentions:
                            mentions = self.asset_resolver.resolve(mentions)
                        if not mentions:
                            content.status = "extracted"
                            result.extracted += 1
                        else:
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

                    processed += 1
                    if on_progress:
                        on_progress(processed, total)

                    if processed % 5 == 0:
                        self.session.commit()

                # Check cancellation before submitting more
                if cancel_check and cancel_check():
                    cancelled = True
                    logger.info("Extraction cancelled at %d/%d", processed, total)
                    break

                # Submit next items
                for _ in range(len(done)):
                    try:
                        content, extractor = next(work_iter)
                        pending.add(pool.submit(_do_extract, content, extractor))
                    except StopIteration:
                        break

            if cancelled:
                # Cancel any remaining pending futures
                for f in pending:
                    f.cancel()

        self.session.commit()
        return result
