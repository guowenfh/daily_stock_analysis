# -*- coding: utf-8 -*-
"""UP主 management API."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import CreatorCreate, CreatorResponse, CreatorUpdate
from src.signal.models import ContentCreator

router = APIRouter()


@router.get("", response_model=list[CreatorResponse])
def list_creators(
    is_active: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ContentCreator)
    if is_active is not None:
        q = q.filter(ContentCreator.is_active == is_active)
    if category:
        q = q.filter(ContentCreator.category == category)
    return q.order_by(ContentCreator.manual_weight.desc()).all()


@router.post("", response_model=CreatorResponse, status_code=201)
def create_creator(
    data: CreatorCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(ContentCreator).filter_by(
        platform=data.platform,
        platform_uid=data.platform_uid,
    ).first()
    if existing:
        raise HTTPException(
            400,
            f"Creator with uid {data.platform_uid} already exists",
        )

    creator = ContentCreator(**data.model_dump())
    db.add(creator)
    db.commit()
    db.refresh(creator)
    return creator


@router.get("/{creator_id}", response_model=CreatorResponse)
def get_creator(creator_id: int, db: Session = Depends(get_db)):
    creator = db.get(ContentCreator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
    return creator


@router.put("/{creator_id}", response_model=CreatorResponse)
def update_creator(
    creator_id: int,
    data: CreatorUpdate,
    db: Session = Depends(get_db),
):
    creator = db.get(ContentCreator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(creator, key, value)

    db.commit()
    db.refresh(creator)
    return creator
