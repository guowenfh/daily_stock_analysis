"""Main signal pipeline orchestration."""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.signal.asset_resolver import AssetResolver
from src.signal.collector import BilibiliCollector
from src.signal.enricher import ContentEnricher
from src.signal.event_builder import SignalEventBuilder
from src.signal.extractor.registry import ExtractorRegistry
from src.signal.quality import QualityTracker

logger = logging.getLogger(__name__)


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

    def run(self, max_contents: int = 50, process_limit: int = 20) -> PipelineResult:
        _ = max_contents  # reserved for future collector limits
        result = PipelineResult(started_at=datetime.utcnow().isoformat())
        t0 = time.time()
        exception_occurred = False

        try:
            collect_step = self._run_collect()
            result.steps.append(collect_step)

            enrich_step = self._run_enrich(process_limit)
            result.steps.append(enrich_step)

            extract_step = self._run_extract(process_limit)
            result.steps.append(extract_step)

            event_step = self._run_events()
            result.steps.append(event_step)

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
            and bool(result.steps)
            and all(s.failed == 0 for s in result.steps)
        )
        return result

    def _run_collect(self) -> StepResult:
        step = StepResult(name="collect", started_at=datetime.utcnow().isoformat())
        try:
            collector = BilibiliCollector(self.session)
            r = collector.fetch_feed()
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
            enricher = ContentEnricher(self.session)
            r = enricher.enrich_batch(limit=limit)
            step.success = r.enriched
            step.skipped = r.skipped
            step.failed = r.failed
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_extract(self, limit: int) -> StepResult:
        step = StepResult(name="extract", started_at=datetime.utcnow().isoformat())
        try:
            registry = ExtractorRegistry(
                self.session, self.extractors, asset_resolver=self.asset_resolver
            )
            r = registry.extract_all(limit=limit)
            step.success = r.extracted
            step.failed = r.failed
            step.skipped = r.skipped
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

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
