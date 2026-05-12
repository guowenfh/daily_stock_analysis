"""Signal pipeline APScheduler integration."""
import logging
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
        self._last_result: Optional[dict[str, Any]] = None
        self._logs: Deque[dict[str, Any]] = deque(maxlen=MAX_LOG_ENTRIES)

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

    def run_now(self):
        self._execute()

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "last_result": self._last_result,
            "job_id": self._job_id,
        }

    def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._logs)[-limit:]

    def _execute(self):
        from src.config import get_config
        from src.storage import DatabaseManager

        logger.info("Signal pipeline execution started")
        start = datetime.utcnow()

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

            from src.signal.pipeline import SignalPipeline

            pipeline = SignalPipeline(session, extractors)
            result = pipeline.run()

            self._last_result = {
                "time": start.isoformat(),
                "success": result.success,
                "elapsed_ms": result.elapsed_ms,
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
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
