# -*- coding: utf-8 -*-
"""Pydantic schemas for signal API endpoints."""
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field


class CreatorCreate(BaseModel):
    platform: str = "bilibili"
    platform_uid: str
    name: str
    category: Optional[str] = None
    is_active: bool = True
    manual_weight: float = Field(default=1.0, ge=0.1, le=2.0)
    fetch_interval_min: int = 60
    notes: Optional[str] = None


class CreatorUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    manual_weight: Optional[float] = Field(default=None, ge=0.1, le=2.0)
    fetch_interval_min: Optional[int] = None
    notes: Optional[str] = None


class CreatorResponse(BaseModel):
    id: int
    platform: str
    platform_uid: str
    name: str
    category: Optional[str]
    is_active: bool
    manual_weight: float
    fetch_interval_min: int
    notes: Optional[str]
    last_fetch_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class QualityStatsResponse(BaseModel):
    total_contents: int
    extracted_count: int
    failed_count: int
    pending_count: int
    ignored_count: int
    extraction_success_rate: float
    active_creators: int
    covered_creators: int
    creator_coverage_rate: float
    failure_explainability_rate: float


class FunnelResponse(BaseModel):
    funnel: dict[str, int]


class FailureItem(BaseModel):
    stage: Optional[str]
    reason: Optional[str]
    count: int


class CreatorStatsItem(BaseModel):
    creator_id: int
    name: str
    total: int
    extracted: int
    failed: int
    success_rate: float
    last_fetch_at: Optional[str]


class ContentListItem(BaseModel):
    id: int
    creator_name: str
    platform_content_id: str
    content_type: str
    display_type: str
    title: Optional[str]
    status: str
    failure_stage: Optional[str]
    failure_reason: Optional[str]
    has_mentions: bool
    published_at: Optional[datetime]
    created_at: Optional[datetime]


class MentionResponse(BaseModel):
    id: int
    content_id: int
    creator_id: int
    creator_name: str
    asset_name: str
    asset_code: Optional[str]
    asset_type: str
    market: str
    sentiment: str
    confidence: float
    is_primary: bool
    reasoning: Optional[str]
    trade_advice: Optional[str]
    key_levels: Optional[dict]
    quality_flags: list[str]
    source_url: Optional[str]
    published_at: Optional[datetime]
    created_at: Optional[datetime]
    content_text: Optional[str] = None
    transcript_text: Optional[str] = None
    summary_text: Optional[str] = None


class EventResponse(BaseModel):
    id: int
    asset_name: str
    asset_code: Optional[str]
    asset_type: str
    market: str
    event_type: str
    event_date: date
    score: Optional[float]
    bullish_count: int
    bearish_count: int
    neutral_count: int
    creator_count: int
    mention_count: int
    top_creator_name: Optional[str]
    evidence: Optional[list[dict]]
    created_at: Optional[datetime]


class PipelineRunResponse(BaseModel):
    status: str
    message: str
