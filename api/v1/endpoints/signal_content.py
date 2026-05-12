# -*- coding: utf-8 -*-
"""Content queue API."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import ContentListItem
from src.signal.models import Content, ContentCreator, SignalMention

router = APIRouter()


@router.get("", response_model=list[ContentListItem])
def list_contents(
    status: Optional[str] = Query(None),
    display_type: Optional[str] = Query(None),
    creator_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(Content)
    if status:
        q = q.filter(Content.status == status)
    if display_type:
        q = q.filter(Content.display_type == display_type)
    if creator_id is not None:
        q = q.filter(Content.creator_id == creator_id)

    contents = q.order_by(Content.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for c in contents:
        creator = db.get(ContentCreator, c.creator_id)
        has_mentions = (
            db.query(SignalMention)
            .filter(SignalMention.content_id == c.id)
            .first()
            is not None
        )
        result.append(
            ContentListItem(
                id=c.id,
                creator_name=creator.name if creator else "unknown",
                platform_content_id=c.platform_content_id,
                content_type=c.content_type,
                display_type=c.display_type,
                title=c.title,
                status=c.status,
                failure_stage=c.failure_stage,
                failure_reason=c.failure_reason,
                has_mentions=has_mentions,
                published_at=c.published_at,
                created_at=c.created_at,
            )
        )
    return result


@router.get("/{content_id}")
def get_content_detail(content_id: int, db: Session = Depends(get_db)):
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(404, "Content not found")

    creator = db.get(ContentCreator, content.creator_id)
    mentions = (
        db.query(SignalMention).filter(SignalMention.content_id == content.id).all()
    )

    return {
        "id": content.id,
        "creator_name": creator.name if creator else "unknown",
        "platform_content_id": content.platform_content_id,
        "content_type": content.content_type,
        "display_type": content.display_type,
        "title": content.title,
        "text": content.text,
        "url": content.url,
        "status": content.status,
        "failure_stage": content.failure_stage,
        "failure_reason": content.failure_reason,
        "suggested_action": content.suggested_action,
        "published_at": content.published_at.isoformat()
        if content.published_at
        else None,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "media": [
            {
                "id": m.id,
                "media_type": m.media_type,
                "url": m.url,
                "ocr_text": m.ocr_text,
            }
            for m in content.media
        ],
        "transcripts": [
            {"id": t.id, "source": t.source, "text": t.text, "quality": t.quality}
            for t in content.transcripts
        ],
        "mentions": [
            {
                "id": m.id,
                "asset_name": m.asset_name,
                "asset_code": m.asset_code,
                "sentiment": m.sentiment,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
            }
            for m in mentions
        ],
    }


@router.post("/{content_id}/retry")
def retry_content(content_id: int, db: Session = Depends(get_db)):
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(404, "Content not found")

    if content.display_type in ("video_subtitle", "image_text"):
        content.status = "pending_enrich"
    else:
        content.status = "pending_extract"

    content.failure_stage = None
    content.failure_reason = None
    content.suggested_action = None
    db.commit()
    return {"status": "ok", "new_status": content.status}


@router.post("/{content_id}/ignore")
def ignore_content(content_id: int, db: Session = Depends(get_db)):
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(404, "Content not found")

    content.status = "ignored"
    db.commit()
    return {"status": "ok"}
