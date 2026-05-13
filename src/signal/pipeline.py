"""Main signal pipeline orchestration."""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.signal.asset_resolver import AssetResolver
from src.signal.collector import BilibiliCollector
from src.signal.enricher import ContentEnricher
from src.signal.event_builder import SignalEventBuilder
from src.signal.extractor.registry import ExtractorRegistry
from src.signal.models import Content
from src.signal.quality import QualityTracker

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass
class StepResult:
    name: str
    started_at: str = ""
    ended_at: str = ""
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[Any] = field(default_factory=list)


@dataclass
class PipelineResult:
    success: bool = True
    started_at: str = ""
    ended_at: str = ""
    elapsed_ms: int = 0
    cancelled: bool = False
    steps: list[StepResult] = field(default_factory=list)
    quality: Optional[dict[str, Any]] = None


class SignalPipeline:
    def __init__(
        self,
        session: Session,
        extractors: Optional[dict] = None,
        asset_resolver: Optional[AssetResolver] = None,
    ):
        self.session = session
        self.extractors = extractors or {}
        self.asset_resolver = asset_resolver

    def run(
        self,
        max_pages: int = 3,
        process_limit: int = 20,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> PipelineResult:
        """Run pipeline. process_limit=0 means process ALL pending items."""
        result = PipelineResult(started_at=datetime.utcnow().isoformat())
        t0 = time.time()
        exception_occurred = False
        self._progress = on_progress or (lambda *a: None)
        self._cancelled = cancel_check or (lambda: False)

        try:
            self._progress("collect", 0, 0, 0, "采集中…")
            if self._cancelled():
                result.cancelled = True
                return result
            collect_step = self._run_collect(max_pages=max_pages)
            result.steps.append(collect_step)

            self._progress("enrich", 1, 0, 0, "富化中…")
            if self._cancelled():
                result.cancelled = True
                return result
            enrich_step = self._run_enrich(process_limit)
            result.steps.append(enrich_step)

            self._progress("extract", 2, 0, 0, "LLM 提取中…")
            if self._cancelled():
                result.cancelled = True
                return result
            extract_step = self._run_extract(process_limit)
            result.steps.append(extract_step)

            self._progress("build_events", 3, 0, 0, "构建事件…")
            if self._cancelled():
                result.cancelled = True
                return result
            event_step = self._run_events()
            result.steps.append(event_step)

            self._progress("compute_stats", 4, 0, 0, "计算统计…")
            stats_step = self._run_stats()
            result.steps.append(stats_step)
            result.quality = stats_step.errors[0] if stats_step.errors else None

        except Exception as e:
            exception_occurred = True
            result.success = False
            logger.exception("Pipeline failed: %s", e)

        result.ended_at = datetime.utcnow().isoformat()
        result.elapsed_ms = int((time.time() - t0) * 1000)
        result.success = (
            not exception_occurred
            and not result.cancelled
            and bool(result.steps)
            and all(s.failed == 0 for s in result.steps)
        )
        return result

    def _get_pending_count(self, status: str) -> int:
        return (
            self.session.query(func.count(Content.id))
            .filter(Content.status == status)
            .scalar()
            or 0
        )

    def _run_collect(self, max_pages: int = 3) -> StepResult:
        step = StepResult(name="collect", started_at=datetime.utcnow().isoformat())
        try:
            collector = BilibiliCollector(self.session)
            r = collector.fetch_feed(max_pages=max_pages)
            step.success = r.new
            step.skipped = r.duplicate + r.skipped
            step.failed = r.failed
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_enrich(self, limit: int) -> StepResult:
        step = StepResult(name="enrich", started_at=datetime.utcnow().isoformat())
        try:
            total = self._get_pending_count("pending_enrich")
            effective_limit = total if limit == 0 else min(limit, total)
            self._progress("enrich", 1, 0, effective_limit, f"富化: 0/{effective_limit}")

            enricher = ContentEnricher(self.session)
            r = enricher.enrich_batch(limit=effective_limit)
            step.success = r.enriched
            step.skipped = r.skipped
            step.failed = r.failed
            step.errors = r.errors
            self._progress("enrich", 1, r.enriched, effective_limit, f"富化完成: {r.enriched}/{effective_limit}")
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_extract(self, limit: int) -> StepResult:
        step = StepResult(name="extract", started_at=datetime.utcnow().isoformat())
        try:
            total = self._get_pending_count("pending_extract")
            effective_limit = total if limit == 0 else min(limit, total)
            self._progress("extract", 2, 0, effective_limit, f"提取: 0/{effective_limit}")

            registry = ExtractorRegistry(
                self.session, self.extractors, asset_resolver=self.asset_resolver
            )
            r = registry.extract_all(
                limit=effective_limit,
                on_progress=self._on_extract_item,
                cancel_check=self._cancelled,
            )
            step.success = r.extracted
            step.failed = r.failed
            step.skipped = r.skipped
            step.errors = r.errors
            self._progress(
                "extract", 2, r.extracted + r.skipped, effective_limit,
                f"提取完成: {r.extracted} 成功, {r.failed} 失败"
            )
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _on_extract_item(self, processed: int, total: int):
        self._progress("extract", 2, processed, total, f"LLM 提取: {processed}/{total}")

    def _run_events(self) -> StepResult:
        step = StepResult(name="build_events", started_at=datetime.utcnow().isoformat())
        try:
            builder = SignalEventBuilder(self.session)
            r = builder.build(date.today())
            step.success = r.created + r.updated
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_stats(self) -> StepResult:
        step = StepResult(name="compute_stats", started_at=datetime.utcnow().isoformat())
        try:
            tracker = QualityTracker(self.session)
            stats = tracker.compute_stats()
            step.success = 1
            step.errors = [stats.__dict__]
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step
