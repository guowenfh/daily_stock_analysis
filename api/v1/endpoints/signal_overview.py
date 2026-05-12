# -*- coding: utf-8 -*-
"""Signal overview API — events and top-level stats."""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import EventResponse, QualityStatsResponse
from src.signal.models import SignalEvent
from src.signal.quality import QualityTracker

router = APIRouter()


@router.get("/events", response_model=list[EventResponse])
def list_events(
    event_type: Optional[str] = Query(None),
    market: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(SignalEvent)
    if event_type:
        q = q.filter(SignalEvent.event_type == event_type)
    if market:
        q = q.filter(SignalEvent.market == market)
    if asset_type:
        q = q.filter(SignalEvent.asset_type == asset_type)
    if date_from:
        q = q.filter(SignalEvent.event_date >= date_from)
    if date_to:
        q = q.filter(SignalEvent.event_date <= date_to)

    events = (
        q.order_by(SignalEvent.score.desc().nulls_last())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        EventResponse(
            id=e.id,
            asset_name=e.asset_name,
            asset_code=e.asset_code,
            asset_type=e.asset_type,
            market=e.market,
            event_type=e.event_type,
            event_date=e.event_date,
            score=e.score,
            bullish_count=e.bullish_count,
            bearish_count=e.bearish_count,
            neutral_count=e.neutral_count,
            creator_count=e.creator_count,
            mention_count=e.mention_count,
            top_creator_name=e.top_creator_name,
            evidence=None,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(SignalEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")

    return EventResponse(
        id=event.id,
        asset_name=event.asset_name,
        asset_code=event.asset_code,
        asset_type=event.asset_type,
        market=event.market,
        event_type=event.event_type,
        event_date=event.event_date,
        score=event.score,
        bullish_count=event.bullish_count,
        bearish_count=event.bearish_count,
        neutral_count=event.neutral_count,
        creator_count=event.creator_count,
        mention_count=event.mention_count,
        top_creator_name=event.top_creator_name,
        evidence=event.get_evidence(),
        created_at=event.created_at,
    )


@router.get("/stats", response_model=QualityStatsResponse)
def get_overview_stats(
    days: int = Query(1, ge=1, le=30),
    db: Session = Depends(get_db),
):
    tracker = QualityTracker(db)
    since = datetime.utcnow() - timedelta(days=days)
    stats = tracker.compute_stats(since=since)
    return QualityStatsResponse(**stats.__dict__)
