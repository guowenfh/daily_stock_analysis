# -*- coding: utf-8 -*-
"""Collection quality dashboard API."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import (
    CreatorStatsItem,
    FailureItem,
    FunnelResponse,
    QualityStatsResponse,
)
from src.signal.quality import QualityTracker

router = APIRouter()


def _parse_since(days: int = 1) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


@router.get("/stats", response_model=QualityStatsResponse)
def get_stats(days: int = Query(1, ge=1, le=30), db: Session = Depends(get_db)):
    tracker = QualityTracker(db)
    stats = tracker.compute_stats(since=_parse_since(days))
    return QualityStatsResponse(**stats.__dict__)


@router.get("/funnel", response_model=FunnelResponse)
def get_funnel(days: int = Query(1, ge=1, le=30), db: Session = Depends(get_db)):
    tracker = QualityTracker(db)
    funnel = tracker.get_funnel(since=_parse_since(days))
    return FunnelResponse(funnel=funnel)


@router.get("/failures", response_model=list[FailureItem])
def get_failures(days: int = Query(1, ge=1, le=30), db: Session = Depends(get_db)):
    tracker = QualityTracker(db)
    return tracker.get_failure_reasons(since=_parse_since(days))


@router.get("/creators", response_model=list[CreatorStatsItem])
def get_creator_stats(
    days: int = Query(1, ge=1, le=30),
    db: Session = Depends(get_db),
):
    tracker = QualityTracker(db)
    return tracker.get_creator_stats(since=_parse_since(days))
