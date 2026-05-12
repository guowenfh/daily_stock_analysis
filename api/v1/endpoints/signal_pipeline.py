# -*- coding: utf-8 -*-
"""Pipeline control API."""
from fastapi import APIRouter, BackgroundTasks

from api.v1.schemas.signal import PipelineRunResponse

router = APIRouter()

_scheduler_instance = None


def get_scheduler():
    global _scheduler_instance
    if _scheduler_instance is None:
        from src.signal.scheduler import SignalScheduler

        _scheduler_instance = SignalScheduler()
    return _scheduler_instance


@router.post("/run", response_model=PipelineRunResponse)
def trigger_pipeline(background_tasks: BackgroundTasks):
    scheduler = get_scheduler()
    background_tasks.add_task(scheduler.run_now)
    return PipelineRunResponse(
        status="started", message="Pipeline run triggered in background"
    )


@router.get("/status")
def pipeline_status():
    scheduler = get_scheduler()
    return scheduler.get_status()


@router.get("/logs")
def pipeline_logs(limit: int = 50):
    scheduler = get_scheduler()
    return scheduler.get_logs(limit=limit)
