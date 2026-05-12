"""Signal system data models.

6 tables: content_creators, contents, content_media,
content_transcripts, signal_mentions, signal_events.
"""
import json
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, Date, DateTime,
    ForeignKey, UniqueConstraint, Index, event,
)
from sqlalchemy.orm import relationship
from src.storage import Base


class ContentCreator(Base):
    __tablename__ = "content_creators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False, default="bilibili")
    platform_uid = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    category = Column(String(64))
    is_active = Column(Boolean, default=True, nullable=False)
    manual_weight = Column(Float, default=1.0, nullable=False)
    fetch_interval_min = Column(Integer, default=60)
    notes = Column(Text)
    last_fetch_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contents = relationship("Content", back_populates="creator")

    __table_args__ = (
        UniqueConstraint("platform", "platform_uid", name="uix_creator_platform_uid"),
    )


class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("content_creators.id"), nullable=False)
    platform = Column(String(32), nullable=False, default="bilibili")
    platform_content_id = Column(String(128), nullable=False)
    content_type = Column(String(32), nullable=False)
    display_type = Column(String(32), nullable=False)
    title = Column(String(512))
    text = Column(Text)
    url = Column(String(1024))
    raw_json = Column(Text)
    status = Column(String(32), nullable=False, default="collected")
    failure_stage = Column(String(32))
    failure_reason = Column(Text)
    suggested_action = Column(String(32))
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("ContentCreator", back_populates="contents")
    media = relationship("ContentMedia", back_populates="content", cascade="all, delete-orphan")
    transcripts = relationship("ContentTranscript", back_populates="content", cascade="all, delete-orphan")
    mentions = relationship("SignalMention", back_populates="content", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("platform", "platform_content_id", name="uix_content_platform_id"),
        Index("ix_content_status", "status"),
        Index("ix_content_creator", "creator_id"),
    )


class ContentMedia(Base):
    __tablename__ = "content_media"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    media_type = Column(String(32), nullable=False)
    url = Column(String(1024))
    ocr_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="media")


class ContentTranscript(Base):
    __tablename__ = "content_transcripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    source = Column(String(32), nullable=False)
    text = Column(Text)
    quality = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="transcripts")


class SignalMention(Base):
    __tablename__ = "signal_mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("content_creators.id"), nullable=False)
    asset_name = Column(String(128), nullable=False)
    asset_code = Column(String(32))
    asset_type = Column(String(32), nullable=False)
    market = Column(String(32), nullable=False, default="unknown")
    sentiment = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=False)
    is_primary = Column(Boolean, default=False)
    reasoning = Column(Text)
    trade_advice = Column(Text)
    key_levels_json = Column(Text)
    quality_flags = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="mentions")
    creator = relationship("ContentCreator")

    def get_quality_flags(self) -> list[str]:
        try:
            return json.loads(self.quality_flags or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def set_quality_flags(self, flags: list[str]):
        self.quality_flags = json.dumps(flags)

    def get_key_levels(self) -> dict:
        try:
            return json.loads(self.key_levels_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}


class SignalEvent(Base):
    __tablename__ = "signal_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_name = Column(String(128), nullable=False)
    asset_code = Column(String(32))
    asset_type = Column(String(32), nullable=False)
    market = Column(String(32), nullable=False)
    event_type = Column(String(32), nullable=False)
    event_date = Column(Date, nullable=False)
    score = Column(Float)
    bullish_count = Column(Integer, default=0)
    bearish_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    creator_count = Column(Integer, default=0)
    mention_count = Column(Integer, default=0)
    top_creator_name = Column(String(128))
    evidence_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("asset_name", "asset_type", "event_date", name="uix_event_asset_date"),
        Index("ix_event_date", "event_date"),
        Index("ix_event_type", "event_type"),
    )

    def get_evidence(self) -> list[dict]:
        try:
            return json.loads(self.evidence_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def set_evidence(self, evidence: list[dict]):
        self.evidence_json = json.dumps(evidence, ensure_ascii=False)


def ensure_signal_tables(engine):
    """Create signal tables if they don't exist."""
    Base.metadata.create_all(engine, tables=[
        ContentCreator.__table__,
        Content.__table__,
        ContentMedia.__table__,
        ContentTranscript.__table__,
        SignalMention.__table__,
        SignalEvent.__table__,
    ])
