# -*- coding: utf-8 -*-
"""Pipeline control API."""
from fastapi import APIRouter, BackgroundTasks, Query

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
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    max_pages: int = Query(3, ge=1, le=50, description="采集翻页上限"),
    process_limit: int = Query(0, ge=0, description="处理上限，0=全部处理"),
):
    scheduler = get_scheduler()
    if scheduler._executing:
        return PipelineRunResponse(
            status="already_running",
            message="Pipeline is already executing",
        )
    background_tasks.add_task(scheduler.run_now, max_pages=max_pages, process_limit=process_limit)
    return PipelineRunResponse(
        status="started",
        message=f"Pipeline run triggered (max_pages={max_pages}, process_limit={process_limit or 'all'})",
    )


@router.post("/cancel")
def cancel_pipeline():
    scheduler = get_scheduler()
    if not scheduler._executing:
        return {"status": "not_running", "message": "No pipeline execution to cancel"}
    scheduler.cancel()
    return {"status": "cancelling", "message": "Cancellation requested"}


@router.get("/status")
def pipeline_status():
    scheduler = get_scheduler()
    return scheduler.get_status()


@router.get("/progress")
def pipeline_progress():
    scheduler = get_scheduler()
    return scheduler.get_progress()


@router.get("/logs")
def pipeline_logs(limit: int = 50):
    scheduler = get_scheduler()
    return scheduler.get_logs(limit=limit)
