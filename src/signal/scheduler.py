"""Signal pipeline APScheduler integration."""
import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Optional

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 50


class SignalScheduler:
    def __init__(self):
        self._scheduler = None
        self._owns_scheduler = False
        self._job_id = "signal_pipeline_hourly"
        self._running = False
        self._executing = False
        self._cancel_requested = False
        self._last_result: Optional[dict[str, Any]] = None
        self._logs: Deque[dict[str, Any]] = deque(maxlen=MAX_LOG_ENTRIES)
        self._progress: dict[str, Any] = {}
        self._lock = threading.Lock()

    def start(self, scheduler=None):
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = BackgroundScheduler()
            self._owns_scheduler = True
            self._scheduler.add_job(
                self._execute,
                CronTrigger(day_of_week="mon-fri", hour="9-23", minute=0),
                id=self._job_id,
                replace_existing=True,
            )
            self._scheduler.start()
        else:
            self._scheduler = scheduler
            self._owns_scheduler = False
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler.add_job(
                self._execute,
                CronTrigger(day_of_week="mon-fri", hour="9-23", minute=0),
                id=self._job_id,
                replace_existing=True,
            )
        self._running = True
        logger.info("Signal scheduler started")

    def stop(self):
        if self._scheduler and self._running:
            try:
                self._scheduler.remove_job(self._job_id)
            except Exception:
                pass
            if self._owns_scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:
                    pass
                self._owns_scheduler = False
            self._running = False
            logger.info("Signal scheduler stopped")

    def run_now(self, max_pages: int = 3, process_limit: int = 0):
        """Run pipeline immediately. process_limit=0 means process all pending."""
        if self._executing:
            logger.warning("Pipeline already executing, skipping")
            return
        self._execute(max_pages=max_pages, process_limit=process_limit)

    def cancel(self):
        """Request cancellation of the running pipeline."""
        if self._executing:
            self._cancel_requested = True
            self._update_progress(message="取消中…")
            logger.info("Pipeline cancellation requested")

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "executing": self._executing,
            "last_result": self._last_result,
            "job_id": self._job_id,
        }

    def get_progress(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._progress)

    def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._logs)[-limit:]

    def _update_progress(self, **kwargs):
        with self._lock:
            self._progress.update(kwargs)

    def _execute(self, max_pages: int = 3, process_limit: int = 0):
        from src.config import get_config
        from src.storage import DatabaseManager

        self._executing = True
        self._cancel_requested = False
        start = datetime.utcnow()
        t0 = time.time()

        with self._lock:
            self._progress = {
                "executing": True,
                "started_at": start.isoformat(),
                "current_step": "init",
                "step_index": 0,
                "total_steps": 5,
                "processed": 0,
                "total": 0,
                "failed": 0,
                "message": "初始化中…",
                "elapsed_ms": 0,
            }

        logger.info(
            "Signal pipeline execution started (max_pages=%d, process_limit=%d)",
            max_pages,
            process_limit,
        )

        session = None
        try:
            db = DatabaseManager.get_instance()
            session = db.get_session()
            config = get_config()

            from src.signal.extractor.text import TextSignalExtractor

            extractors = {
                "text": TextSignalExtractor(litellm_model=config.litellm_model),
            }

            try:
                from src.signal.extractor.video import VideoSignalExtractor

                extractors["video_subtitle"] = VideoSignalExtractor(
                    litellm_model=config.litellm_model
                )
            except ImportError:
                pass
            try:
                from src.signal.extractor.image import ImageSignalExtractor

                extractors["image_text"] = ImageSignalExtractor(
                    litellm_model=config.litellm_model
                )
            except ImportError:
                pass

            from src.signal.asset_resolver import AssetResolver
            from src.signal.pipeline import SignalPipeline

            resolver = AssetResolver()
            pipeline = SignalPipeline(session, extractors, asset_resolver=resolver)
            result = pipeline.run(
                max_pages=max_pages,
                process_limit=process_limit,
                on_progress=self._on_pipeline_progress,
                cancel_check=lambda: self._cancel_requested,
            )

            elapsed_ms = int((time.time() - t0) * 1000)
            self._last_result = {
                "time": start.isoformat(),
                "success": result.success,
                "elapsed_ms": elapsed_ms,
                "cancelled": self._cancel_requested,
                "steps": [
                    {"name": s.name, "success": s.success, "failed": s.failed}
                    for s in result.steps
                ],
            }
            self._logs.append(self._last_result)

        except Exception as e:
            logger.exception("Signal pipeline execution failed: %s", e)
            self._last_result = {
                "time": start.isoformat(),
                "success": False,
                "error": str(e),
            }
            self._logs.append(self._last_result)
        finally:
            self._executing = False
            self._cancel_requested = False
            with self._lock:
                self._progress = {
                    "executing": False,
                    "started_at": start.isoformat(),
                    "finished_at": datetime.utcnow().isoformat(),
                    "current_step": "done",
                    "message": "完成" if self._last_result and self._last_result.get("success") else "失败",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def _on_pipeline_progress(self, step: str, step_index: int, processed: int, total: int, message: str = ""):
        elapsed_key = "elapsed_ms"
        started = self._progress.get("started_at", "")
        self._update_progress(
            current_step=step,
            step_index=step_index,
            processed=processed,
            total=total,
            message=message or f"{step}: {processed}/{total}",
        )
