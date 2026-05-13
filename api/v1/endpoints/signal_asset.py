# -*- coding: utf-8 -*-
"""Asset detail API — per-asset signals and timeline."""
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from api.deps import get_db
from api.v1.schemas.signal import MentionResponse
from src.signal.models import Content, ContentCreator, SignalEvent, SignalMention

router = APIRouter()

_TRANSCRIPT_QUALITY_PRIORITY = {"good": 0, "short": 1, "title_only": 2, "failed": 3}


def _best_transcript_text(content: Optional[Content]) -> Optional[str]:
    """Pick the best non-summary transcript (same priority as video extractor)."""
    if not content:
        return None
    transcripts = content.transcripts or []
    non_summary = [
        t for t in transcripts if getattr(t, "source", None) != "llm_summary"
    ]
    if not non_summary:
        return None
    sorted_t = sorted(
        non_summary,
        key=lambda t: _TRANSCRIPT_QUALITY_PRIORITY.get(t.quality, 99),
    )
    best = sorted_t[0]
    if best and best.quality != "failed":
        return best.text
    return None


def _llm_summary_transcript(content: Optional[Content]) -> Optional[str]:
    if not content:
        return None
    for t in content.transcripts or []:
        if (
            getattr(t, "source", None) == "llm_summary"
            and getattr(t, "quality", None) == "summarized"
            and t.text
        ):
            return t.text
    return None


def _resolve_asset(identifier: str, db: Session):
    identifier = unquote(identifier)
    mentions = (
        db.query(SignalMention)
        .filter(
            (SignalMention.asset_code == identifier)
            | (SignalMention.asset_name == identifier)
        )
        .all()
    )
    return mentions, identifier


@router.get("/{identifier}")
def get_asset_detail(identifier: str, db: Session = Depends(get_db)):
    mentions, resolved = _resolve_asset(identifier, db)
    if not mentions:
        raise HTTPException(404, f"No signals found for {resolved}")

    first = mentions[0]
    event = (
        db.query(SignalEvent)
        .filter(
            (SignalEvent.asset_code == first.asset_code)
            | (SignalEvent.asset_name == first.asset_name)
        )
        .order_by(SignalEvent.event_date.desc())
        .first()
    )

    bullish = sum(1 for m in mentions if m.sentiment == "bullish")
    bearish = sum(1 for m in mentions if m.sentiment == "bearish")
    neutral = sum(1 for m in mentions if m.sentiment == "neutral")

    creator_ids = {m.creator_id for m in mentions}
    creators = {
        c.id: c
        for c in db.query(ContentCreator)
        .filter(ContentCreator.id.in_(creator_ids))
        .all()
    }

    return {
        "asset_name": first.asset_name,
        "asset_code": first.asset_code,
        "asset_type": first.asset_type,
        "market": first.market,
        "event": {
            "event_type": event.event_type,
            "score": event.score,
            "event_date": event.event_date.isoformat(),
        }
        if event
        else None,
        "sentiment_summary": {
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
        },
        "creator_count": len(creator_ids),
        "mention_count": len(mentions),
        "creators": [
            {"id": c.id, "name": c.name, "weight": c.manual_weight}
            for c in creators.values()
        ],
    }


@router.get("/{identifier}/mentions", response_model=list[MentionResponse])
def get_asset_mentions(
    identifier: str,
    sentiment: Optional[str] = Query(None),
    creator_id: Optional[int] = Query(None),
    include_content: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    identifier = unquote(identifier)
    q = db.query(SignalMention).filter(
        (SignalMention.asset_code == identifier)
        | (SignalMention.asset_name == identifier)
    )
    if sentiment:
        q = q.filter(SignalMention.sentiment == sentiment)
    if creator_id is not None:
        q = q.filter(SignalMention.creator_id == creator_id)
    if include_content:
        q = q.options(
            selectinload(SignalMention.content).selectinload(Content.transcripts)
        )

    mentions = (
        q.order_by(SignalMention.created_at.desc()).offset(offset).limit(limit).all()
    )

    result = []
    for m in mentions:
        creator = db.get(ContentCreator, m.creator_id)
        content = m.content if include_content else db.get(Content, m.content_id)
        content_text = None
        transcript_text = None
        summary_text = None
        if include_content and content:
            content_text = content.text
            transcript_text = _best_transcript_text(content)
            summary_text = _llm_summary_transcript(content)
        result.append(
            MentionResponse(
                id=m.id,
                content_id=m.content_id,
                creator_id=m.creator_id,
                creator_name=creator.name if creator else "unknown",
                asset_name=m.asset_name,
                asset_code=m.asset_code,
                asset_type=m.asset_type,
                market=m.market,
                sentiment=m.sentiment,
                confidence=m.confidence,
                is_primary=m.is_primary,
                reasoning=m.reasoning,
                trade_advice=m.trade_advice,
                key_levels=m.get_key_levels(),
                quality_flags=m.get_quality_flags(),
                source_url=content.url if content else None,
                published_at=content.published_at if content else None,
                created_at=m.created_at,
                content_text=content_text,
                transcript_text=transcript_text,
                summary_text=summary_text,
            )
        )
    return result


@router.get("/{identifier}/timeline")
def get_asset_timeline(
    identifier: str,
    db: Session = Depends(get_db),
):
    identifier = unquote(identifier)
    mentions = (
        db.query(SignalMention)
        .filter(
            (SignalMention.asset_code == identifier)
            | (SignalMention.asset_name == identifier)
        )
        .order_by(SignalMention.created_at.asc())
        .all()
    )

    timeline = []
    for m in mentions:
        creator = db.get(ContentCreator, m.creator_id)
        content = db.get(Content, m.content_id)
        timeline.append(
            {
                "date": m.created_at.isoformat() if m.created_at else None,
                "creator_name": creator.name if creator else "unknown",
                "sentiment": m.sentiment,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "content_title": content.title if content else "",
                "source_url": content.url if content else "",
            }
        )
    return timeline
