"""Signal system data models.

6 tables: content_creators, contents, content_media,
content_transcripts, signal_mentions, signal_events.
"""
import json
import re
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, Date, DateTime,
    ForeignKey, UniqueConstraint, Index, event, text,
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
    """Create signal tables if they don't exist and align old local schemas."""
    Base.metadata.create_all(engine, tables=[
        ContentCreator.__table__,
        Content.__table__,
        ContentMedia.__table__,
        ContentTranscript.__table__,
        SignalMention.__table__,
        SignalEvent.__table__,
    ])
    _migrate_sqlite_signal_tables(engine)


def _migrate_sqlite_signal_tables(engine):
    """Rebuild legacy SQLite signal tables to match the current ORM models."""
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        _rebuild_sqlite_table_if_needed(
            conn,
            ContentCreator.__table__,
            {
                "id": "id",
                "platform": "COALESCE(platform, 'bilibili')",
                "platform_uid": "platform_uid",
                "name": "name",
                "category": "category",
                "is_active": "COALESCE(is_active, 1)",
                "manual_weight": "COALESCE(manual_weight, 1.0)",
                "fetch_interval_min": "fetch_interval_min",
                "notes": "notes",
                "last_fetch_at": _coalesce_existing("last_fetch_at", "last_fetched_at"),
                "created_at": "created_at",
                "updated_at": "updated_at",
            },
        )
        _rebuild_sqlite_table_if_needed(
            conn,
            Content.__table__,
            {
                "id": "id",
                "creator_id": "creator_id",
                "platform": "COALESCE(platform, 'bilibili')",
                "platform_content_id": "COALESCE(platform_content_id, 'legacy-' || id)",
                "content_type": "COALESCE(content_type, 'dynamic')",
                "display_type": (
                    "COALESCE(display_type, "
                    "CASE WHEN subtitle IS NOT NULL OR subtitle_raw IS NOT NULL "
                    "THEN 'video_subtitle' WHEN has_image = 1 THEN 'image_text' ELSE 'text' END)"
                ),
                "title": "title",
                "text": _coalesce_existing("NULLIF(text, '')", "plain_text", "subtitle", "description"),
                "url": _coalesce_existing("NULLIF(url, '')", "cover_url"),
                "raw_json": "raw_json",
                "status": "COALESCE(status, CASE WHEN processed = 1 THEN 'extracted' ELSE 'collected' END)",
                "failure_stage": "failure_stage",
                "failure_reason": _coalesce_existing("failure_reason", "process_error"),
                "suggested_action": "suggested_action",
                "published_at": _coalesce_existing("published_at", "publish_time"),
                "created_at": _coalesce_existing("created_at", "fetched_at"),
                "updated_at": _coalesce_existing("updated_at", "update_time"),
            },
        )
        _rebuild_sqlite_table_if_needed(
            conn,
            ContentMedia.__table__,
            {
                "id": "id",
                "content_id": "content_id",
                "media_type": "COALESCE(media_type, 'image')",
                "url": _coalesce_existing("url", "media_url", "thumbnail_url"),
                "ocr_text": _coalesce_existing("ocr_text", "image_text"),
                "created_at": "created_at",
            },
        )
        _rebuild_sqlite_table_if_needed(
            conn,
            ContentTranscript.__table__,
            {
                "id": "id",
                "content_id": "content_id",
                "source": (
                    "CASE "
                    "WHEN source IN ('platform', 'whisper', 'manual', 'llm_summary') THEN source "
                    "WHEN lower(COALESCE(source, platform, '')) = 'bilibili' THEN 'platform' "
                    "WHEN COALESCE(source, platform, '') != '' THEN COALESCE(source, platform) "
                    "ELSE 'platform' END"
                ),
                "text": "text",
                "quality": (
                    "CASE WHEN quality IS NULL OR quality = '' OR quality = 'unknown' "
                    "THEN CASE WHEN length(COALESCE(text, '')) >= 50 THEN 'good' ELSE 'short' END "
                    "ELSE quality END"
                ),
                "created_at": "created_at",
            },
        )
        _rebuild_sqlite_table_if_needed(
            conn,
            SignalMention.__table__,
            {column.name: column.name for column in SignalMention.__table__.columns},
        )
        _rebuild_sqlite_table_if_needed(
            conn,
            SignalEvent.__table__,
            {
                "id": "id",
                "asset_name": "asset_name",
                "asset_code": "asset_code",
                "asset_type": "COALESCE(asset_type, 'stock')",
                "market": "COALESCE(market, 'unknown')",
                "event_type": _coalesce_existing("event_type", "direction", "'mention'"),
                "event_date": "event_date",
                "score": _coalesce_existing("score", "strength", "0"),
                "bullish_count": "COALESCE(bullish_count, 0)",
                "bearish_count": "COALESCE(bearish_count, 0)",
                "neutral_count": "COALESCE(neutral_count, 0)",
                "creator_count": _coalesce_existing("creator_count", "uploader_count", "0"),
                "mention_count": "COALESCE(mention_count, 0)",
                "top_creator_name": "top_creator_name",
                "evidence_json": "evidence_json",
                "created_at": "created_at",
                "updated_at": "updated_at",
            },
        )
        conn.execute(text("PRAGMA foreign_keys=ON"))


def _coalesce_existing(*expressions: str) -> str:
    return f"COALESCE({', '.join(expressions)})"


def _sqlite_columns(conn, table_name: str) -> list[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in rows]


def _rebuild_sqlite_table_if_needed(conn, table, column_exprs: dict[str, str]):
    table_name = table.name
    existing_columns = _sqlite_columns(conn, table_name)
    if not existing_columns:
        return

    target_columns = [column.name for column in table.columns]
    if existing_columns == target_columns and not _has_legacy_sqlite_foreign_keys(conn, table_name):
        return

    available = set(existing_columns)
    tmp_name = f"{table_name}__legacy_signal_migration"
    conn.execute(text(f"DROP TABLE IF EXISTS {tmp_name}"))
    conn.execute(text(f"ALTER TABLE {table_name} RENAME TO {tmp_name}"))

    for row in conn.execute(text(f"PRAGMA index_list({tmp_name})")).fetchall():
        index_name = row[1]
        origin = row[3] if len(row) > 3 else ""
        if origin != "pk" and not index_name.startswith("sqlite_autoindex"):
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    table.create(bind=conn)

    select_exprs = []
    for column in target_columns:
        expr = column_exprs.get(column, "NULL")
        select_exprs.append(f"{_rewrite_missing_columns(expr, available)} AS {column}")

    conn.execute(
        text(
            f"INSERT INTO {table_name} ({', '.join(target_columns)}) "
            f"SELECT {', '.join(select_exprs)} FROM {tmp_name}"
        )
    )
    conn.execute(text(f"DROP TABLE {tmp_name}"))


def _rewrite_missing_columns(expr: str, available: set[str]) -> str:
    """Replace references to columns absent from a legacy table with NULL."""
    known = {
        "id", "platform", "platform_uid", "name", "category", "is_active",
        "manual_weight", "fetch_interval_min", "notes", "last_fetch_at",
        "last_fetched_at", "created_at", "updated_at", "creator_id",
        "platform_content_id", "content_type", "display_type", "subtitle",
        "subtitle_raw", "has_image", "title", "text", "plain_text",
        "description", "url", "cover_url", "raw_json", "status", "processed",
        "failure_stage", "failure_reason", "process_error", "suggested_action",
        "published_at", "publish_time", "fetched_at", "update_time",
        "content_id", "media_type", "media_url", "thumbnail_url", "ocr_text",
        "image_text", "source", "platform", "quality", "asset_name",
        "asset_code", "asset_type", "market", "event_type", "direction",
        "event_date", "score", "strength", "bullish_count", "bearish_count",
        "neutral_count", "creator_count", "uploader_count", "mention_count",
        "top_creator_name", "evidence_json", "sentiment", "confidence",
        "is_primary", "reasoning", "trade_advice", "key_levels_json",
        "quality_flags",
    }
    for column in sorted(known - available, key=len, reverse=True):
        expr = re.sub(rf"\b{re.escape(column)}\b", "NULL", expr)
    return expr


def _has_legacy_sqlite_foreign_keys(conn, table_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA foreign_key_list({table_name})")).fetchall()
    return any("__legacy_signal_migration" in str(row[2]) for row in rows)
