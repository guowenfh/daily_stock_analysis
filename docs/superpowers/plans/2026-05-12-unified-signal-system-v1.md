# 统一信号系统 V1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零实现 Bilibili 信号提取链路 V1 —— 采集→补全→提取→事件聚合→5 个前端页面，作为 `src/signal/` 独立子包。

**Architecture:** 新建 `src/signal/` 子包，共享现有 SQLAlchemy Base、FastAPI app、APScheduler。后端 Python + 前端 React/TypeScript。主链路：collect → enrich → extract → build_events → compute_stats。

**Tech Stack:** Python 3.11+, SQLAlchemy, FastAPI, LiteLLM, APScheduler, React 19, TypeScript, Tailwind 4, axios, react-router-dom

**Spec:** `docs/superpowers/specs/2026-05-12-unified-signal-system-v1-design.md`

---

## File Structure

### Backend — Create

```
src/signal/__init__.py
src/signal/models.py
src/signal/collector.py
src/signal/enricher.py
src/signal/quality.py
src/signal/event_builder.py
src/signal/pipeline.py
src/signal/scheduler.py
src/signal/prompt_manager.py
src/signal/extractor/__init__.py
src/signal/extractor/base.py
src/signal/extractor/text.py
src/signal/extractor/image.py
src/signal/extractor/video.py
src/signal/extractor/registry.py
config/prompts/signal_text.yaml
config/prompts/signal_image.yaml
config/prompts/signal_video.yaml
```

### API — Create

```
api/v1/endpoints/signal_creators.py
api/v1/endpoints/signal_quality.py
api/v1/endpoints/signal_content.py
api/v1/endpoints/signal_overview.py
api/v1/endpoints/signal_asset.py
api/v1/endpoints/signal_pipeline.py
api/v1/schemas/signal.py
```

### API — Modify

```
api/v1/router.py               — add signal route includes
api/v1/endpoints/__init__.py    — add signal imports (if needed)
```

### Frontend — Create

```
apps/dsa-web/src/types/signal.ts
apps/dsa-web/src/api/signal.ts
apps/dsa-web/src/pages/signal/SignalOverviewPage.tsx
apps/dsa-web/src/pages/signal/QualityDashboard.tsx
apps/dsa-web/src/pages/signal/ContentQueuePage.tsx
apps/dsa-web/src/pages/signal/AssetDetailPage.tsx
apps/dsa-web/src/pages/signal/CreatorManagePage.tsx
apps/dsa-web/src/pages/signal/index.ts
```

### Frontend — Modify

```
apps/dsa-web/src/App.tsx                          — add /signals routes
apps/dsa-web/src/components/layout/SidebarNav.tsx  — add signal nav items
```

### Tests — Create

```
tests/signal/__init__.py
tests/signal/conftest.py
tests/signal/test_models.py
tests/signal/test_collector.py
tests/signal/test_enricher.py
tests/signal/test_extractor.py
tests/signal/test_event_builder.py
tests/signal/test_quality.py
tests/signal/test_pipeline.py
tests/signal/test_api_creators.py
```

---

## Task 1: Signal 数据模型

**Milestone:** M1.1

**Files:**
- Create: `src/signal/__init__.py`
- Create: `src/signal/models.py`
- Create: `tests/signal/__init__.py`
- Create: `tests/signal/conftest.py`
- Create: `tests/signal/test_models.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p src/signal/extractor tests/signal
touch src/signal/__init__.py src/signal/extractor/__init__.py tests/signal/__init__.py
```

- [ ] **Step 2: Write signal models**

Create `src/signal/models.py`:

```python
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
```

- [ ] **Step 3: Write `src/signal/__init__.py`**

```python
"""Unified Signal System V1.

Bilibili content → structured signals → single-asset events.
"""
from src.signal.models import (
    ContentCreator,
    Content,
    ContentMedia,
    ContentTranscript,
    SignalMention,
    SignalEvent,
    ensure_signal_tables,
)

__all__ = [
    "ContentCreator",
    "Content",
    "ContentMedia",
    "ContentTranscript",
    "SignalMention",
    "SignalEvent",
    "ensure_signal_tables",
]
```

- [ ] **Step 4: Write test fixtures**

Create `tests/signal/conftest.py`:

```python
"""Shared fixtures for signal tests."""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session with all signal tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()
```

- [ ] **Step 5: Write model tests**

Create `tests/signal/test_models.py`:

```python
"""Tests for signal data models."""
from datetime import datetime, date

from src.signal.models import (
    ContentCreator, Content, ContentMedia, ContentTranscript,
    SignalMention, SignalEvent,
)


class TestContentCreator:
    def test_create_creator(self, db_session):
        creator = ContentCreator(
            platform="bilibili",
            platform_uid="12345",
            name="测试UP主",
            category="财经",
            manual_weight=1.5,
        )
        db_session.add(creator)
        db_session.commit()

        loaded = db_session.query(ContentCreator).first()
        assert loaded.name == "测试UP主"
        assert loaded.manual_weight == 1.5
        assert loaded.is_active is True

    def test_unique_platform_uid(self, db_session):
        c1 = ContentCreator(platform="bilibili", platform_uid="111", name="A")
        c2 = ContentCreator(platform="bilibili", platform_uid="111", name="B")
        db_session.add(c1)
        db_session.commit()
        db_session.add(c2)
        import sqlalchemy
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db_session.commit()


class TestContent:
    def test_create_content_with_creator(self, db_session):
        creator = ContentCreator(platform="bilibili", platform_uid="1", name="UP1")
        db_session.add(creator)
        db_session.flush()

        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id="dyn_123",
            content_type="dynamic",
            display_type="text",
            title="测试动态",
            text="今天聊聊茅台",
            status="collected",
        )
        db_session.add(content)
        db_session.commit()

        loaded = db_session.query(Content).first()
        assert loaded.creator.name == "UP1"
        assert loaded.status == "collected"

    def test_status_transitions(self, db_session):
        creator = ContentCreator(platform="bilibili", platform_uid="2", name="UP2")
        db_session.add(creator)
        db_session.flush()

        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id="v_456",
            content_type="video",
            display_type="video_subtitle",
            status="collected",
        )
        db_session.add(content)
        db_session.commit()

        content.status = "pending_enrich"
        db_session.commit()
        assert content.status == "pending_enrich"

        content.status = "failed"
        content.failure_stage = "enrich"
        content.failure_reason = "Whisper timeout"
        content.suggested_action = "retry"
        db_session.commit()
        assert content.failure_stage == "enrich"


class TestSignalMention:
    def test_quality_flags_json(self, db_session):
        creator = ContentCreator(platform="bilibili", platform_uid="3", name="UP3")
        db_session.add(creator)
        db_session.flush()
        content = Content(
            creator_id=creator.id, platform="bilibili",
            platform_content_id="x", content_type="dynamic",
            display_type="text", status="extracted",
        )
        db_session.add(content)
        db_session.flush()

        mention = SignalMention(
            content_id=content.id,
            creator_id=creator.id,
            asset_name="贵州茅台",
            asset_code="600519",
            asset_type="stock",
            market="a_share",
            sentiment="bullish",
            confidence=0.85,
            is_primary=True,
        )
        mention.set_quality_flags(["no_trade_advice"])
        db_session.add(mention)
        db_session.commit()

        loaded = db_session.query(SignalMention).first()
        assert loaded.get_quality_flags() == ["no_trade_advice"]
        assert loaded.get_key_levels() == {}


class TestSignalEvent:
    def test_create_event(self, db_session):
        ev = SignalEvent(
            asset_name="贵州茅台",
            asset_code="600519",
            asset_type="stock",
            market="a_share",
            event_type="opportunity",
            event_date=date(2026, 5, 12),
            score=85.0,
            bullish_count=3,
            bearish_count=0,
            neutral_count=1,
            creator_count=3,
            mention_count=4,
            top_creator_name="财经老王",
        )
        ev.set_evidence([{"mention_id": 1, "sentiment": "bullish"}])
        db_session.add(ev)
        db_session.commit()

        loaded = db_session.query(SignalEvent).first()
        assert loaded.score == 85.0
        assert loaded.get_evidence()[0]["sentiment"] == "bullish"

    def test_unique_constraint(self, db_session):
        base = dict(
            asset_name="茅台", asset_type="stock", market="a_share",
            event_type="opportunity", event_date=date(2026, 5, 12),
        )
        db_session.add(SignalEvent(**base))
        db_session.commit()
        db_session.add(SignalEvent(**base))
        import sqlalchemy
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db_session.commit()


import pytest
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/signal/test_models.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/signal/ tests/signal/
git commit -m "feat(signal): add 6 signal data models with tests

ContentCreator, Content, ContentMedia, ContentTranscript,
SignalMention, SignalEvent — foundational models for V1."
```

---

## Task 2: BilibiliCollector

**Milestone:** M1.2

**Files:**
- Create: `src/signal/collector.py`
- Create: `tests/signal/test_collector.py`

- [ ] **Step 1: Write BilibiliCollector**

Create `src/signal/collector.py`:

```python
"""Bilibili content collector using bili CLI."""
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import yaml

from src.signal.models import ContentCreator, Content, ContentMedia

logger = logging.getLogger(__name__)

CONTENT_TYPE_MAP = {
    "MAJOR_TYPE_ARCHIVE": "video",
    "MAJOR_TYPE_COMMON": "article",
    "MAJOR_TYPE_OPUS": "article",
    "MAJOR_TYPE_DRAW": "image",
}

DISPLAY_TYPE_MAP = {
    "video": "video_subtitle",
    "image": "image_text",
    "article": "text",
    "dynamic": "text",
    "forward": "text",
}


@dataclass
class CollectResult:
    new: int = 0
    duplicate: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class BilibiliCollector:
    def __init__(self, session):
        self.session = session

    def fetch_feed(self, max_retries: int = 3, timeout: int = 60) -> CollectResult:
        result = CollectResult()
        raw_items = self._call_bili_feed(max_retries, timeout)
        if raw_items is None:
            result.failed = 1
            result.errors.append("bili feed command failed after retries")
            return result

        creators = self._load_active_creators()
        creator_by_uid = {c.platform_uid: c for c in creators}
        creator_by_name = {c.name: c for c in creators}

        for item in raw_items:
            try:
                self._process_item(item, creator_by_uid, creator_by_name, result)
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Error processing item: {e}")
                logger.exception("Failed to process feed item")

        self.session.commit()
        return result

    def _call_bili_feed(self, max_retries: int, timeout: int) -> Optional[list]:
        for attempt in range(max_retries):
            try:
                proc = subprocess.run(
                    ["bili", "feed", "--yaml"],
                    capture_output=True, text=True, timeout=timeout,
                )
                if proc.returncode != 0:
                    logger.warning("bili feed failed (attempt %d): %s", attempt + 1, proc.stderr[:200])
                    continue
                data = yaml.safe_load(proc.stdout)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "items" in data:
                    return data["items"]
                return data if data else []
            except subprocess.TimeoutExpired:
                logger.warning("bili feed timed out (attempt %d)", attempt + 1)
            except Exception as e:
                logger.warning("bili feed error (attempt %d): %s", attempt + 1, e)
        return None

    def _load_active_creators(self) -> list[ContentCreator]:
        return self.session.query(ContentCreator).filter(
            ContentCreator.is_active == True,
            ContentCreator.platform == "bilibili",
        ).all()

    def _match_creator(
        self, uid: str, name: str,
        by_uid: dict, by_name: dict,
    ) -> Optional[ContentCreator]:
        if uid and uid in by_uid:
            return by_uid[uid]
        if name and name in by_name:
            return by_name[name]
        return None

    def _process_item(self, item: dict, by_uid: dict, by_name: dict, result: CollectResult):
        author = item.get("author", {}) or {}
        uid = str(author.get("mid", "") or item.get("uid", ""))
        name = author.get("name", "") or item.get("author_name", "")

        creator = self._match_creator(uid, name, by_uid, by_name)
        if creator is None:
            result.skipped += 1
            return

        dynamic_id = str(item.get("id", "") or item.get("dynamic_id", ""))
        bvid = item.get("bvid", "")
        platform_content_id = bvid or dynamic_id
        if not platform_content_id:
            result.skipped += 1
            return

        existing = self.session.query(Content).filter_by(
            platform="bilibili",
            platform_content_id=platform_content_id,
        ).first()
        if existing:
            result.duplicate += 1
            return

        major_type = item.get("type", "") or item.get("major_type", "")
        content_type = CONTENT_TYPE_MAP.get(major_type, "dynamic")
        display_type = DISPLAY_TYPE_MAP.get(content_type, "text")

        title = item.get("title", "")
        text = item.get("text", "") or item.get("desc", "")
        url = item.get("url", "")
        if bvid and not url:
            url = f"https://www.bilibili.com/video/{bvid}"

        pub_ts = item.get("pub_ts") or item.get("publish_time")
        published_at = None
        if pub_ts:
            try:
                published_at = datetime.fromtimestamp(int(pub_ts))
            except (ValueError, TypeError, OSError):
                pass

        initial_status = "pending_enrich" if display_type != "text" else "pending_extract"

        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id=platform_content_id,
            content_type=content_type,
            display_type=display_type,
            title=title,
            text=text,
            url=url,
            raw_json=json.dumps(item, ensure_ascii=False),
            status=initial_status,
            published_at=published_at,
        )
        self.session.add(content)
        self.session.flush()

        images = item.get("images", []) or []
        for img_url in images:
            if isinstance(img_url, str):
                media = ContentMedia(
                    content_id=content.id,
                    media_type="image",
                    url=img_url,
                )
                self.session.add(media)

        creator.last_fetch_at = datetime.utcnow()
        result.new += 1
```

- [ ] **Step 2: Write collector tests**

Create `tests/signal/test_collector.py`:

```python
"""Tests for BilibiliCollector."""
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

from src.signal.models import ContentCreator, Content, ContentMedia
from src.signal.collector import BilibiliCollector, CollectResult


class TestBilibiliCollector:
    def _setup_creator(self, db_session):
        creator = ContentCreator(
            platform="bilibili", platform_uid="12345",
            name="财经老王", category="财经",
        )
        db_session.add(creator)
        db_session.flush()
        return creator

    @patch("src.signal.collector.subprocess.run")
    def test_fetch_feed_new_dynamic(self, mock_run, db_session):
        self._setup_creator(db_session)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""
- id: "dyn_001"
  author:
    mid: 12345
    name: "财经老王"
  type: "MAJOR_TYPE_OPUS"
  title: "聊聊茅台"
  text: "今天茅台走势不错"
  url: "https://t.bilibili.com/dyn_001"
  pub_ts: 1715500000
""",
        )

        collector = BilibiliCollector(db_session)
        result = collector.fetch_feed()

        assert result.new == 1
        assert result.duplicate == 0

        content = db_session.query(Content).first()
        assert content.platform_content_id == "dyn_001"
        assert content.content_type == "article"
        assert content.display_type == "text"
        assert content.status == "pending_extract"

    @patch("src.signal.collector.subprocess.run")
    def test_skip_unknown_creator(self, mock_run, db_session):
        self._setup_creator(db_session)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""
- id: "dyn_002"
  author:
    mid: 99999
    name: "未知UP主"
  type: "MAJOR_TYPE_OPUS"
  text: "some text"
""",
        )

        collector = BilibiliCollector(db_session)
        result = collector.fetch_feed()
        assert result.skipped == 1
        assert result.new == 0

    @patch("src.signal.collector.subprocess.run")
    def test_duplicate_skipped(self, mock_run, db_session):
        creator = self._setup_creator(db_session)
        content = Content(
            creator_id=creator.id, platform="bilibili",
            platform_content_id="dyn_dup", content_type="dynamic",
            display_type="text", status="collected",
        )
        db_session.add(content)
        db_session.flush()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""
- id: "dyn_dup"
  author:
    mid: 12345
    name: "财经老王"
  text: "dup"
""",
        )

        collector = BilibiliCollector(db_session)
        result = collector.fetch_feed()
        assert result.duplicate == 1
        assert result.new == 0

    @patch("src.signal.collector.subprocess.run")
    def test_video_gets_pending_enrich(self, mock_run, db_session):
        self._setup_creator(db_session)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""
- bvid: "BV1test123"
  author:
    mid: 12345
    name: "财经老王"
  type: "MAJOR_TYPE_ARCHIVE"
  title: "视频标题"
  pub_ts: 1715500000
""",
        )

        collector = BilibiliCollector(db_session)
        result = collector.fetch_feed()
        assert result.new == 1

        content = db_session.query(Content).first()
        assert content.display_type == "video_subtitle"
        assert content.status == "pending_enrich"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/signal/test_collector.py -v
```

Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/signal/collector.py tests/signal/test_collector.py
git commit -m "feat(signal): add BilibiliCollector with bili CLI integration"
```

---

## Task 3: QualityTracker

**Milestone:** M1.3

**Files:**
- Create: `src/signal/quality.py`
- Create: `tests/signal/test_quality.py`

- [ ] **Step 1: Write QualityTracker**

Create `src/signal/quality.py`:

```python
"""Collection and extraction quality tracking."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.signal.models import Content, ContentCreator

logger = logging.getLogger(__name__)


@dataclass
class QualityStats:
    total_contents: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    ignored_count: int = 0
    extraction_success_rate: float = 0.0
    active_creators: int = 0
    covered_creators: int = 0
    creator_coverage_rate: float = 0.0
    explainable_failures: int = 0
    failure_explainability_rate: float = 0.0


class QualityTracker:
    def __init__(self, session: Session):
        self.session = session

    def compute_stats(self, since: Optional[datetime] = None) -> QualityStats:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        stats = QualityStats()

        status_counts = (
            self.session.query(Content.status, func.count(Content.id))
            .filter(Content.created_at >= since)
            .group_by(Content.status)
            .all()
        )
        status_map = dict(status_counts)

        stats.total_contents = sum(status_map.values())
        stats.extracted_count = status_map.get("extracted", 0) + status_map.get("low_confidence", 0)
        stats.failed_count = status_map.get("failed", 0)
        stats.ignored_count = status_map.get("ignored", 0)
        stats.pending_count = (
            status_map.get("collected", 0)
            + status_map.get("pending_enrich", 0)
            + status_map.get("pending_extract", 0)
        )

        processable = stats.total_contents - stats.ignored_count
        if processable > 0:
            stats.extraction_success_rate = stats.extracted_count / processable

        stats.active_creators = self.session.query(ContentCreator).filter(
            ContentCreator.is_active == True,
        ).count()

        stats.covered_creators = (
            self.session.query(func.count(func.distinct(Content.creator_id)))
            .filter(Content.created_at >= since)
            .scalar()
        ) or 0

        if stats.active_creators > 0:
            stats.creator_coverage_rate = stats.covered_creators / stats.active_creators

        if stats.failed_count > 0:
            stats.explainable_failures = (
                self.session.query(Content)
                .filter(
                    Content.status == "failed",
                    Content.created_at >= since,
                    Content.failure_stage.isnot(None),
                    Content.failure_reason.isnot(None),
                )
                .count()
            )
            stats.failure_explainability_rate = stats.explainable_failures / stats.failed_count

        return stats

    def get_funnel(self, since: Optional[datetime] = None) -> dict[str, int]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        rows = (
            self.session.query(Content.status, func.count(Content.id))
            .filter(Content.created_at >= since)
            .group_by(Content.status)
            .all()
        )
        return dict(rows)

    def get_failure_reasons(self, since: Optional[datetime] = None, limit: int = 20) -> list[dict]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        rows = (
            self.session.query(
                Content.failure_stage,
                Content.failure_reason,
                func.count(Content.id).label("count"),
            )
            .filter(Content.status == "failed", Content.created_at >= since)
            .group_by(Content.failure_stage, Content.failure_reason)
            .order_by(func.count(Content.id).desc())
            .limit(limit)
            .all()
        )
        return [
            {"stage": r[0], "reason": r[1], "count": r[2]}
            for r in rows
        ]

    def get_creator_stats(self, since: Optional[datetime] = None) -> list[dict]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        creators = self.session.query(ContentCreator).filter(
            ContentCreator.is_active == True,
        ).all()

        result = []
        for c in creators:
            total = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.created_at >= since,
            ).count()
            extracted = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.status.in_(["extracted", "low_confidence"]),
                Content.created_at >= since,
            ).count()
            failed = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.status == "failed",
                Content.created_at >= since,
            ).count()
            result.append({
                "creator_id": c.id,
                "name": c.name,
                "total": total,
                "extracted": extracted,
                "failed": failed,
                "success_rate": extracted / total if total > 0 else 0.0,
                "last_fetch_at": c.last_fetch_at.isoformat() if c.last_fetch_at else None,
            })

        return result
```

- [ ] **Step 2: Write quality tests**

Create `tests/signal/test_quality.py`:

```python
"""Tests for QualityTracker."""
from datetime import datetime

import pytest

from src.signal.models import ContentCreator, Content
from src.signal.quality import QualityTracker


class TestQualityTracker:
    def _add_creator(self, session, uid="1", name="UP1"):
        c = ContentCreator(platform="bilibili", platform_uid=uid, name=name)
        session.add(c)
        session.flush()
        return c

    def _add_content(self, session, creator_id, pid, status="extracted", **kwargs):
        c = Content(
            creator_id=creator_id, platform="bilibili",
            platform_content_id=pid, content_type="dynamic",
            display_type="text", status=status, **kwargs,
        )
        session.add(c)
        session.flush()
        return c

    def test_compute_stats_basic(self, db_session):
        c = self._add_creator(db_session)
        self._add_content(db_session, c.id, "p1", status="extracted")
        self._add_content(db_session, c.id, "p2", status="extracted")
        self._add_content(db_session, c.id, "p3", status="failed",
                          failure_stage="extract", failure_reason="LLM error")
        db_session.commit()

        tracker = QualityTracker(db_session)
        stats = tracker.compute_stats(since=datetime(2020, 1, 1))
        assert stats.total_contents == 3
        assert stats.extracted_count == 2
        assert stats.failed_count == 1
        assert stats.extraction_success_rate == pytest.approx(2 / 3, rel=0.01)
        assert stats.failure_explainability_rate == 1.0

    def test_funnel(self, db_session):
        c = self._add_creator(db_session)
        self._add_content(db_session, c.id, "a", status="collected")
        self._add_content(db_session, c.id, "b", status="pending_extract")
        self._add_content(db_session, c.id, "c", status="extracted")
        db_session.commit()

        tracker = QualityTracker(db_session)
        funnel = tracker.get_funnel(since=datetime(2020, 1, 1))
        assert funnel["collected"] == 1
        assert funnel["pending_extract"] == 1
        assert funnel["extracted"] == 1

    def test_creator_coverage(self, db_session):
        c1 = self._add_creator(db_session, "1", "A")
        c2 = self._add_creator(db_session, "2", "B")
        self._add_content(db_session, c1.id, "x", status="extracted")
        db_session.commit()

        tracker = QualityTracker(db_session)
        stats = tracker.compute_stats(since=datetime(2020, 1, 1))
        assert stats.active_creators == 2
        assert stats.covered_creators == 1
        assert stats.creator_coverage_rate == 0.5
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/signal/test_quality.py -v
```

Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/signal/quality.py tests/signal/test_quality.py
git commit -m "feat(signal): add QualityTracker for collection stats"
```

---

## Task 4: API Schemas + Creators API + Quality API + Router

**Milestone:** M1.4, M1.5

**Files:**
- Create: `api/v1/schemas/signal.py`
- Create: `api/v1/endpoints/signal_creators.py`
- Create: `api/v1/endpoints/signal_quality.py`
- Modify: `api/v1/router.py`
- Create: `tests/signal/test_api_creators.py`

- [ ] **Step 1: Write Pydantic schemas**

Create `api/v1/schemas/signal.py`:

```python
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
```

- [ ] **Step 2: Write Creators API**

Create `api/v1/endpoints/signal_creators.py`:

```python
"""UP主 management API."""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import CreatorCreate, CreatorUpdate, CreatorResponse
from src.signal.models import ContentCreator

router = APIRouter()


@router.get("", response_model=list[CreatorResponse])
def list_creators(
    is_active: bool = Query(None),
    category: str = Query(None),
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
        platform=data.platform, platform_uid=data.platform_uid,
    ).first()
    if existing:
        raise HTTPException(400, f"Creator with uid {data.platform_uid} already exists")

    creator = ContentCreator(**data.model_dump())
    db.add(creator)
    db.commit()
    db.refresh(creator)
    return creator


@router.get("/{creator_id}", response_model=CreatorResponse)
def get_creator(creator_id: int, db: Session = Depends(get_db)):
    creator = db.query(ContentCreator).get(creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
    return creator


@router.put("/{creator_id}", response_model=CreatorResponse)
def update_creator(
    creator_id: int,
    data: CreatorUpdate,
    db: Session = Depends(get_db),
):
    creator = db.query(ContentCreator).get(creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(creator, key, value)

    db.commit()
    db.refresh(creator)
    return creator
```

- [ ] **Step 3: Write Quality API**

Create `api/v1/endpoints/signal_quality.py`:

```python
"""Collection quality dashboard API."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.v1.schemas.signal import QualityStatsResponse, FunnelResponse, FailureItem, CreatorStatsItem
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
def get_creator_stats(days: int = Query(1, ge=1, le=30), db: Session = Depends(get_db)):
    tracker = QualityTracker(db)
    return tracker.get_creator_stats(since=_parse_since(days))
```

- [ ] **Step 4: Register signal routes in router**

Modify `api/v1/router.py` — add these imports and include_router calls after the existing ones:

```python
from api.v1.endpoints import signal_creators, signal_quality

router.include_router(
    signal_creators.router,
    prefix="/signals/creators",
    tags=["Signal - Creators"],
)

router.include_router(
    signal_quality.router,
    prefix="/signals/quality",
    tags=["Signal - Quality"],
)
```

- [ ] **Step 5: Write API integration test**

Create `tests/signal/test_api_creators.py`:

```python
"""Integration tests for signal creators API."""
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.storage import DatabaseManager, Base
from src.signal.models import ensure_signal_tables


@pytest.fixture
def client():
    DatabaseManager.reset_instance()
    os.environ["DATABASE_PATH"] = ":memory:"

    from src.config import Config
    Config._instance = None

    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    ensure_signal_tables(db_manager._engine)

    from api.app import create_app
    app = create_app()
    with patch("api.deps.get_database_manager", return_value=db_manager):
        with TestClient(app) as c:
            yield c

    DatabaseManager.reset_instance()


class TestCreatorsAPI:
    def test_create_and_list(self, client):
        resp = client.post("/api/v1/signals/creators", json={
            "platform_uid": "12345",
            "name": "测试UP主",
            "category": "财经",
            "manual_weight": 1.5,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试UP主"
        assert data["manual_weight"] == 1.5

        resp = client.get("/api/v1/signals/creators")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_update_creator(self, client):
        client.post("/api/v1/signals/creators", json={
            "platform_uid": "111", "name": "A",
        })
        resp = client.put("/api/v1/signals/creators/1", json={
            "manual_weight": 0.5, "is_active": False,
        })
        assert resp.status_code == 200
        assert resp.json()["manual_weight"] == 0.5
        assert resp.json()["is_active"] is False

    def test_duplicate_uid_rejected(self, client):
        client.post("/api/v1/signals/creators", json={
            "platform_uid": "222", "name": "B",
        })
        resp = client.post("/api/v1/signals/creators", json={
            "platform_uid": "222", "name": "C",
        })
        assert resp.status_code == 400
```

- [ ] **Step 6: Run all signal tests**

```bash
python -m pytest tests/signal/ -v
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add api/v1/schemas/signal.py api/v1/endpoints/signal_creators.py api/v1/endpoints/signal_quality.py api/v1/router.py tests/signal/test_api_creators.py
git commit -m "feat(signal): add Creators CRUD + Quality API endpoints"
```

---

## Task 5: SignalEventBuilder

**Milestone:** M4.1-M4.3

**Files:**
- Create: `src/signal/event_builder.py`
- Create: `tests/signal/test_event_builder.py`

- [ ] **Step 1: Write SignalEventBuilder**

Create `src/signal/event_builder.py`:

```python
"""Aggregate signal mentions into single-asset events."""
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from src.signal.models import SignalMention, SignalEvent, ContentCreator, Content

logger = logging.getLogger(__name__)


@dataclass
class EventBuildResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


class SignalEventBuilder:
    def __init__(self, session: Session):
        self.session = session

    def build(self, target_date: date) -> EventBuildResult:
        result = EventBuildResult()

        mentions = (
            self.session.query(SignalMention)
            .join(Content, SignalMention.content_id == Content.id)
            .filter(
                Content.status.in_(["extracted", "low_confidence"]),
                SignalMention.created_at >= target_date.isoformat(),
            )
            .all()
        )

        grouped = defaultdict(list)
        for m in mentions:
            key = (m.asset_name, m.asset_type)
            grouped[key].append(m)

        for (asset_name, asset_type), group in grouped.items():
            try:
                self._build_event(asset_name, asset_type, group, target_date, result)
            except Exception as e:
                result.errors.append(f"Error building event for {asset_name}: {e}")
                logger.exception("Failed to build event for %s", asset_name)

        self.session.commit()
        return result

    def _build_event(
        self,
        asset_name: str,
        asset_type: str,
        mentions: list[SignalMention],
        target_date: date,
        result: EventBuildResult,
    ):
        bullish = [m for m in mentions if m.sentiment == "bullish"]
        bearish = [m for m in mentions if m.sentiment == "bearish"]
        neutral = [m for m in mentions if m.sentiment == "neutral"]

        creator_ids = set(m.creator_id for m in mentions)
        creator_count = len(creator_ids)

        creators = {
            c.id: c for c in
            self.session.query(ContentCreator).filter(
                ContentCreator.id.in_(creator_ids)
            ).all()
        }

        event_type = self._classify_event(
            bullish, bearish, neutral, creators, mentions,
        )
        score = self._compute_score(mentions, creators)

        top_creator = max(
            creators.values(),
            key=lambda c: c.manual_weight,
            default=None,
        )

        asset_code = next((m.asset_code for m in mentions if m.asset_code), None)
        market = mentions[0].market if mentions else "unknown"

        evidence = self._build_evidence(mentions, creators)

        existing = self.session.query(SignalEvent).filter_by(
            asset_name=asset_name, asset_type=asset_type, event_date=target_date,
        ).first()

        if existing:
            existing.event_type = event_type
            existing.score = score
            existing.bullish_count = len(bullish)
            existing.bearish_count = len(bearish)
            existing.neutral_count = len(neutral)
            existing.creator_count = creator_count
            existing.mention_count = len(mentions)
            existing.top_creator_name = top_creator.name if top_creator else None
            existing.set_evidence(evidence)
            existing.asset_code = asset_code
            result.updated += 1
        else:
            ev = SignalEvent(
                asset_name=asset_name,
                asset_code=asset_code,
                asset_type=asset_type,
                market=market,
                event_type=event_type,
                event_date=target_date,
                score=score,
                bullish_count=len(bullish),
                bearish_count=len(bearish),
                neutral_count=len(neutral),
                creator_count=creator_count,
                mention_count=len(mentions),
                top_creator_name=top_creator.name if top_creator else None,
            )
            ev.set_evidence(evidence)
            self.session.add(ev)
            result.created += 1

    def _classify_event(
        self,
        bullish: list, bearish: list, neutral: list,
        creators: dict, all_mentions: list,
    ) -> str:
        total = len(bullish) + len(bearish) + len(neutral)
        if total == 0:
            return "watch"

        bull_ratio = len(bullish) / total
        bear_ratio = len(bearish) / total

        bull_creators = set(m.creator_id for m in bullish)
        bear_creators = set(m.creator_id for m in bearish)

        has_high_weight_bull = any(
            creators.get(cid) and creators[cid].manual_weight >= 1.5
            for cid in bull_creators
        )
        has_high_weight_bear = any(
            creators.get(cid) and creators[cid].manual_weight >= 1.5
            for cid in bear_creators
        )

        if len(bull_creators) >= 2 and len(bear_creators) >= 2:
            return "conflict"

        if bull_ratio >= 0.6 and len(bull_creators) >= 2:
            return "opportunity"
        if has_high_weight_bull and bull_ratio >= 0.5:
            return "opportunity"

        if bear_ratio >= 0.6 and len(bear_creators) >= 2:
            return "risk"
        if has_high_weight_bear and bear_ratio >= 0.5:
            return "risk"

        return "watch"

    def _compute_score(self, mentions: list[SignalMention], creators: dict) -> float:
        if not mentions:
            return 0.0

        total = len(mentions)

        bullish = sum(1 for m in mentions if m.sentiment == "bullish")
        bearish = sum(1 for m in mentions if m.sentiment == "bearish")
        sentiment_strength = abs(bullish - bearish) / total
        sentiment_score = sentiment_strength * 100

        avg_confidence = sum(m.confidence for m in mentions) / total
        confidence_score = avg_confidence * 100

        creator_ids = set(m.creator_id for m in mentions)
        max_weight = max(
            (creators.get(cid, None) for cid in creator_ids),
            key=lambda c: c.manual_weight if c else 0,
            default=None,
        )
        weight_score = min(len(creator_ids) * 20, 60)
        if max_weight and max_weight.manual_weight >= 1.5:
            weight_score = min(weight_score + 30, 100)

        advice_count = sum(1 for m in mentions if m.trade_advice)
        advice_score = (advice_count / total) * 100

        primary_count = sum(1 for m in mentions if m.is_primary)
        primary_score = (primary_count / total) * 100

        final = (
            sentiment_score * 0.30
            + confidence_score * 0.20
            + weight_score * 0.30
            + advice_score * 0.10
            + primary_score * 0.10
        )
        return round(min(max(final, 0), 100), 1)

    def _build_evidence(self, mentions: list[SignalMention], creators: dict) -> list[dict]:
        evidence = []
        for m in mentions:
            creator = creators.get(m.creator_id)
            content = self.session.query(Content).get(m.content_id)
            evidence.append({
                "mention_id": m.id,
                "content_id": m.content_id,
                "creator_id": m.creator_id,
                "creator_name": creator.name if creator else "unknown",
                "creator_weight": creator.manual_weight if creator else 1.0,
                "content_title": content.title if content else "",
                "content_type": content.content_type if content else "",
                "display_type": content.display_type if content else "",
                "sentiment": m.sentiment,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "trade_advice": m.trade_advice,
                "source_url": content.url if content else "",
                "published_at": content.published_at.isoformat() if content and content.published_at else None,
            })
        return evidence
```

- [ ] **Step 2: Write event builder tests**

Create `tests/signal/test_event_builder.py`:

```python
"""Tests for SignalEventBuilder."""
from datetime import date, datetime

import pytest

from src.signal.models import ContentCreator, Content, SignalMention, SignalEvent
from src.signal.event_builder import SignalEventBuilder


class TestSignalEventBuilder:
    def _setup(self, db_session, n_creators=2, n_mentions_per=1, sentiments=None):
        creators = []
        for i in range(n_creators):
            c = ContentCreator(
                platform="bilibili", platform_uid=str(100 + i),
                name=f"UP{i}", manual_weight=1.0 + i * 0.5,
            )
            db_session.add(c)
            creators.append(c)
        db_session.flush()

        contents = []
        mentions = []
        if sentiments is None:
            sentiments = ["bullish"] * n_creators
        for i, creator in enumerate(creators):
            for j in range(n_mentions_per):
                content = Content(
                    creator_id=creator.id, platform="bilibili",
                    platform_content_id=f"c_{i}_{j}",
                    content_type="dynamic", display_type="text",
                    status="extracted",
                )
                db_session.add(content)
                db_session.flush()
                contents.append(content)

                mention = SignalMention(
                    content_id=content.id, creator_id=creator.id,
                    asset_name="贵州茅台", asset_code="600519",
                    asset_type="stock", market="a_share",
                    sentiment=sentiments[i],
                    confidence=0.8, is_primary=True,
                )
                db_session.add(mention)
                mentions.append(mention)
        db_session.flush()
        return creators, contents, mentions

    def test_opportunity_event(self, db_session):
        self._setup(db_session, n_creators=3, sentiments=["bullish", "bullish", "bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        result = builder.build(date.today())

        assert result.created == 1
        event = db_session.query(SignalEvent).first()
        assert event.event_type == "opportunity"
        assert event.bullish_count == 3
        assert event.creator_count == 3
        assert event.asset_name == "贵州茅台"

    def test_conflict_event(self, db_session):
        self._setup(db_session, n_creators=4,
                     sentiments=["bullish", "bullish", "bearish", "bearish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        result = builder.build(date.today())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "conflict"

    def test_risk_event(self, db_session):
        self._setup(db_session, n_creators=3,
                     sentiments=["bearish", "bearish", "bearish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        result = builder.build(date.today())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "risk"

    def test_watch_event_single_mention(self, db_session):
        self._setup(db_session, n_creators=1, sentiments=["bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        result = builder.build(date.today())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "watch"

    def test_evidence_populated(self, db_session):
        self._setup(db_session, n_creators=2, sentiments=["bullish", "bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        builder.build(date.today())

        event = db_session.query(SignalEvent).first()
        evidence = event.get_evidence()
        assert len(evidence) == 2
        assert evidence[0]["sentiment"] == "bullish"
        assert "creator_name" in evidence[0]

    def test_update_existing_event(self, db_session):
        self._setup(db_session, n_creators=2, sentiments=["bullish", "bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        r1 = builder.build(date.today())
        assert r1.created == 1

        r2 = builder.build(date.today())
        assert r2.updated == 1
        assert db_session.query(SignalEvent).count() == 1
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/signal/test_event_builder.py -v
```

Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/signal/event_builder.py tests/signal/test_event_builder.py
git commit -m "feat(signal): add SignalEventBuilder with scoring and classification"
```

---

## Task 6: Extractor 基础设施 + TextSignalExtractor

**Milestone:** M3.1-M3.4

**Files:**
- Create: `src/signal/extractor/base.py`
- Create: `src/signal/extractor/text.py`
- Create: `src/signal/extractor/registry.py`
- Create: `src/signal/prompt_manager.py`
- Create: `config/prompts/signal_text.yaml`
- Create: `tests/signal/test_extractor.py`

- [ ] **Step 1: Write BaseExtractor and MentionData**

Create `src/signal/extractor/base.py`:

```python
"""Base extractor interface and shared types."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MentionData:
    name: str
    code: Optional[str] = None
    asset_type: str = "stock"
    market: str = "unknown"
    sentiment: str = "neutral"
    confidence: float = 0.5
    is_primary: bool = False
    reasoning: Optional[str] = None
    trade_advice: Optional[str] = None
    key_levels: Optional[dict] = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    extracted: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, content) -> list[MentionData]:
        """Extract signal mentions from content. Returns list of MentionData."""
        ...

    def _apply_quality_rules(self, mentions: list[MentionData], content) -> list[MentionData]:
        for m in mentions:
            if not m.code:
                if "code_unresolved" not in m.quality_flags:
                    m.quality_flags.append("code_unresolved")
            if not m.trade_advice:
                if "no_trade_advice" not in m.quality_flags:
                    m.quality_flags.append("no_trade_advice")
            if m.confidence < 0.4:
                if "low_llm_confidence" not in m.quality_flags:
                    m.quality_flags.append("low_llm_confidence")
        return mentions
```

- [ ] **Step 2: Write PromptManager**

Create `src/signal/prompt_manager.py`:

```python
"""Load and render YAML prompt templates."""
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "config" / "prompts"


class PromptManager:
    _cache: dict[str, dict] = {}

    @classmethod
    def get_prompt(cls, display_type: str) -> Optional[str]:
        filename = f"signal_{display_type}.yaml"
        if filename not in cls._cache:
            path = PROMPTS_DIR / filename
            if not path.exists():
                logger.warning("Prompt file not found: %s", path)
                return None
            with open(path, "r", encoding="utf-8") as f:
                cls._cache[filename] = yaml.safe_load(f)

        data = cls._cache.get(filename, {})
        return data.get("system_prompt", "")

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
```

- [ ] **Step 3: Write text prompt YAML**

Create `config/prompts/signal_text.yaml`:

```yaml
system_prompt: |
  你是一个专业的财经内容信号提取器。你的任务是从以下文本内容中提取所有被提及的股票、ETF、指数和板块，以及作者对它们的观点。

  规则：
  - 提取内容中出现的每一个资产（股票、ETF、指数、板块）
  - 主要讨论的标的标记 is_primary=true，顺带提及的标记 is_primary=false
  - sentiment 只能是 bullish / bearish / neutral
  - confidence 范围 0.0-1.0，反映作者观点的明确程度
  - reasoning 必须引用原文证据
  - trade_advice 只填写作者明确给出的操作建议，没有则留空字符串
  - key_levels 填写作者提到的具体价位，没有则为空对象
  - asset_type: stock / etf / index / sector
  - market: a_share / hk / us / unknown
  - code: 股票代码（如 600519），不确定则留空字符串

  输出严格 JSON 格式：
  {
    "mentions": [
      {
        "name": "标的名称",
        "code": "代码或空字符串",
        "asset_type": "stock",
        "market": "a_share",
        "sentiment": "bullish",
        "confidence": 0.8,
        "is_primary": true,
        "reasoning": "原文证据摘录",
        "trade_advice": "操作建议原文或空字符串",
        "key_levels": {"support": [], "resistance": []}
      }
    ]
  }
```

- [ ] **Step 4: Write TextSignalExtractor**

Create `src/signal/extractor/text.py`:

```python
"""Text content signal extractor."""
import json
import logging
import re
from typing import Optional

from src.signal.extractor.base import BaseExtractor, MentionData

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20


class TextSignalExtractor(BaseExtractor):
    def __init__(self, litellm_model: str, temperature: float = 0.3, max_tokens: int = 8192):
        self.model = litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def extract(self, content) -> list[MentionData]:
        text = content.text or ""
        title = content.title or ""
        full_text = f"{title}\n{text}".strip()

        if len(full_text) < MIN_TEXT_LENGTH:
            logger.debug("Text too short (%d chars), skipping", len(full_text))
            return []

        from src.signal.prompt_manager import PromptManager
        system_prompt = PromptManager.get_prompt("text")
        if not system_prompt:
            return []

        try:
            import litellm
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_text},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content
            data = self._parse_json(raw)
            mentions = self._to_mention_data(data)
            return self._apply_quality_rules(mentions, content)

        except Exception as e:
            logger.exception("LLM extraction failed: %s", e)
            return []

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        return json.loads(raw)

    def _to_mention_data(self, data: dict) -> list[MentionData]:
        mentions_raw = data.get("mentions", [])
        result = []
        for m in mentions_raw:
            if not m.get("name"):
                continue
            result.append(MentionData(
                name=m["name"],
                code=m.get("code") or None,
                asset_type=m.get("asset_type", "stock"),
                market=m.get("market", "unknown"),
                sentiment=m.get("sentiment", "neutral"),
                confidence=float(m.get("confidence", 0.5)),
                is_primary=bool(m.get("is_primary", False)),
                reasoning=m.get("reasoning"),
                trade_advice=m.get("trade_advice") or None,
                key_levels=m.get("key_levels"),
            ))
        return result
```

- [ ] **Step 5: Write ExtractorRegistry**

Create `src/signal/extractor/registry.py`:

```python
"""Extractor dispatch by display_type."""
import json
import logging
from dataclasses import field

from sqlalchemy.orm import Session

from src.signal.models import Content, SignalMention
from src.signal.extractor.base import BaseExtractor, MentionData, ExtractResult

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    def __init__(self, session: Session, extractors: dict[str, BaseExtractor]):
        self.session = session
        self.extractors = extractors

    def extract_all(self, contents: list[Content] = None, limit: int = 20) -> ExtractResult:
        result = ExtractResult()

        if contents is None:
            contents = (
                self.session.query(Content)
                .filter(Content.status == "pending_extract")
                .limit(limit)
                .all()
            )

        for content in contents:
            extractor = self.extractors.get(content.display_type)
            if not extractor:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = f"No extractor for display_type={content.display_type}"
                result.failed += 1
                continue

            try:
                mentions = extractor.extract(content)
                if not mentions:
                    content.status = "extracted"
                    result.extracted += 1
                    continue

                for m_data in mentions:
                    mention = SignalMention(
                        content_id=content.id,
                        creator_id=content.creator_id,
                        asset_name=m_data.name,
                        asset_code=m_data.code,
                        asset_type=m_data.asset_type,
                        market=m_data.market,
                        sentiment=m_data.sentiment,
                        confidence=m_data.confidence,
                        is_primary=m_data.is_primary,
                        reasoning=m_data.reasoning,
                        trade_advice=m_data.trade_advice,
                        key_levels_json=json.dumps(m_data.key_levels or {}, ensure_ascii=False),
                    )
                    mention.set_quality_flags(m_data.quality_flags)
                    self.session.add(mention)

                content.status = "extracted"
                result.extracted += 1

            except Exception as e:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = str(e)[:500]
                result.failed += 1
                result.errors.append(f"Content {content.id}: {e}")
                logger.exception("Extraction failed for content %d", content.id)

        self.session.commit()
        return result
```

- [ ] **Step 6: Write `src/signal/extractor/__init__.py`**

```python
from src.signal.extractor.base import BaseExtractor, MentionData, ExtractResult
from src.signal.extractor.registry import ExtractorRegistry

__all__ = ["BaseExtractor", "MentionData", "ExtractResult", "ExtractorRegistry"]
```

- [ ] **Step 7: Write extractor tests**

Create `tests/signal/test_extractor.py`:

```python
"""Tests for signal extractors."""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.signal.models import ContentCreator, Content, SignalMention
from src.signal.extractor.base import MentionData
from src.signal.extractor.text import TextSignalExtractor
from src.signal.extractor.registry import ExtractorRegistry


class TestTextSignalExtractor:
    @patch("src.signal.extractor.text.litellm")
    def test_extract_basic(self, mock_litellm, db_session):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "mentions": [{
                "name": "贵州茅台", "code": "600519",
                "asset_type": "stock", "market": "a_share",
                "sentiment": "bullish", "confidence": 0.85,
                "is_primary": True,
                "reasoning": "茅台走势不错",
                "trade_advice": "", "key_levels": {},
            }]
        })
        mock_litellm.completion.return_value = mock_response

        content = MagicMock()
        content.text = "今天茅台走势不错，600519 值得关注"
        content.title = "聊聊茅台"

        extractor = TextSignalExtractor(litellm_model="test-model")
        with patch("src.signal.extractor.text.PromptManager") as pm:
            pm.get_prompt.return_value = "system prompt"
            mentions = extractor.extract(content)

        assert len(mentions) == 1
        assert mentions[0].name == "贵州茅台"
        assert mentions[0].sentiment == "bullish"
        assert "no_trade_advice" in mentions[0].quality_flags

    def test_skip_short_text(self, db_session):
        content = MagicMock()
        content.text = "短"
        content.title = ""

        extractor = TextSignalExtractor(litellm_model="test")
        mentions = extractor.extract(content)
        assert len(mentions) == 0


class TestExtractorRegistry:
    def _setup(self, db_session):
        creator = ContentCreator(
            platform="bilibili", platform_uid="1", name="UP1",
        )
        db_session.add(creator)
        db_session.flush()

        content = Content(
            creator_id=creator.id, platform="bilibili",
            platform_content_id="test_1", content_type="dynamic",
            display_type="text", title="测试", text="茅台600519看多",
            status="pending_extract",
        )
        db_session.add(content)
        db_session.flush()
        return creator, content

    def test_extract_all_writes_mentions(self, db_session):
        creator, content = self._setup(db_session)

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            MentionData(name="茅台", code="600519", sentiment="bullish",
                        confidence=0.9, is_primary=True, asset_type="stock"),
        ]

        registry = ExtractorRegistry(db_session, {"text": mock_extractor})
        result = registry.extract_all()

        assert result.extracted == 1
        assert content.status == "extracted"
        mention = db_session.query(SignalMention).first()
        assert mention.asset_name == "茅台"
        assert mention.sentiment == "bullish"

    def test_no_extractor_marks_failed(self, db_session):
        creator, content = self._setup(db_session)
        content.display_type = "unknown_type"
        db_session.flush()

        registry = ExtractorRegistry(db_session, {})
        result = registry.extract_all()

        assert result.failed == 1
        assert content.status == "failed"
        assert content.failure_stage == "extract"
```

- [ ] **Step 8: Run tests**

```bash
python -m pytest tests/signal/test_extractor.py -v
```

Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add src/signal/extractor/ src/signal/prompt_manager.py config/prompts/signal_text.yaml tests/signal/test_extractor.py
git commit -m "feat(signal): add extractor framework + TextSignalExtractor + prompts"
```

---

## Task 7: Video + Image 提取器 + Prompts

**Milestone:** M3.2-M3.3

**Files:**
- Create: `src/signal/extractor/video.py`
- Create: `src/signal/extractor/image.py`
- Create: `config/prompts/signal_video.yaml`
- Create: `config/prompts/signal_image.yaml`

- [ ] **Step 1: Write video prompt**

Create `config/prompts/signal_video.yaml` — same structure as `signal_text.yaml` but with instructions to first extract from title, then scan subtitle line by line; emphasize that trade_advice must be based on the creator's actual words, not inferred from the title alone.

- [ ] **Step 2: Write image prompt**

Create `config/prompts/signal_image.yaml` — same output contract but with instructions to analyze K-line charts, position screenshots, sector heatmaps, and combine text + image information.

- [ ] **Step 3: Write VideoSignalExtractor**

Create `src/signal/extractor/video.py` — follows the same pattern as `TextSignalExtractor`, but:
- Gets subtitle from `content.transcripts` relationship (priority: good > short > title_only)
- Falls back to `content.title` if no transcript
- If using title-only fallback, caps confidence at 0.4 and adds `title_only` quality flag
- If transcript has quality=`short`, adds `subtitle_missing` flag

- [ ] **Step 4: Write ImageSignalExtractor**

Create `src/signal/extractor/image.py` — follows `TextSignalExtractor` pattern but:
- Collects `content.media` images (max 10)
- Builds Vision LLM messages with image URLs
- Falls back to text-only extraction if no images or Vision LLM unavailable
- Adds `image_ocr_incomplete` flag if image processing partially fails

- [ ] **Step 5: Run all extractor tests**

```bash
python -m pytest tests/signal/test_extractor.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/signal/extractor/video.py src/signal/extractor/image.py config/prompts/signal_video.yaml config/prompts/signal_image.yaml
git commit -m "feat(signal): add Video + Image extractors with prompts"
```

---

## Task 8: ContentEnricher

**Milestone:** M2.1-M2.3

**Files:**
- Create: `src/signal/enricher.py`
- Create: `tests/signal/test_enricher.py`

- [ ] **Step 1: Write ContentEnricher**

Create `src/signal/enricher.py` with:
- `enrich_batch()`: queries `status=pending_enrich`, dispatches to `_enrich_video` or `_enrich_image`
- `_enrich_video()`: runs `bili video <bvid> --subtitle --yaml`, parses result; on failure runs Whisper (with 300s timeout, single-task lock); saves `ContentTranscript`
- `_enrich_image()`: for image_text content with media, runs Vision LLM to OCR; updates `content_media.ocr_text`
- On success: sets `content.status = "pending_extract"`
- On failure: sets `content.status = "failed"`, records `failure_stage = "enrich"` and reason

- [ ] **Step 2: Write enricher tests (mocked subprocess + LLM)**

Create `tests/signal/test_enricher.py` with tests for:
- Video with platform subtitle available → transcript saved, quality=good
- Video without subtitle, Whisper fallback → quality depends on length
- Image enrichment → ocr_text populated
- Failure handling → status=failed with reason

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/signal/test_enricher.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/signal/enricher.py tests/signal/test_enricher.py
git commit -m "feat(signal): add ContentEnricher for subtitle + OCR enrichment"
```

---

## Task 9: SignalPipeline + Scheduler

**Milestone:** M5.1-M5.2

**Files:**
- Create: `src/signal/pipeline.py`
- Create: `src/signal/scheduler.py`
- Create: `tests/signal/test_pipeline.py`

- [ ] **Step 1: Write SignalPipeline**

Create `src/signal/pipeline.py`:

```python
"""Main signal pipeline orchestration."""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.signal.collector import BilibiliCollector, CollectResult
from src.signal.enricher import ContentEnricher
from src.signal.extractor.registry import ExtractorRegistry, ExtractResult
from src.signal.event_builder import SignalEventBuilder, EventBuildResult
from src.signal.quality import QualityTracker, QualityStats

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    name: str
    started_at: str = ""
    ended_at: str = ""
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    success: bool = True
    started_at: str = ""
    ended_at: str = ""
    elapsed_ms: int = 0
    steps: list[StepResult] = field(default_factory=list)
    quality: Optional[dict] = None


class SignalPipeline:
    def __init__(self, session: Session, extractors: dict = None):
        self.session = session
        self.extractors = extractors or {}

    def run(self, max_contents: int = 50, process_limit: int = 20) -> PipelineResult:
        result = PipelineResult(started_at=datetime.utcnow().isoformat())
        t0 = time.time()

        try:
            collect_step = self._run_collect()
            result.steps.append(collect_step)

            enrich_step = self._run_enrich(process_limit)
            result.steps.append(enrich_step)

            extract_step = self._run_extract(process_limit)
            result.steps.append(extract_step)

            event_step = self._run_events()
            result.steps.append(event_step)

            stats_step = self._run_stats()
            result.steps.append(stats_step)
            result.quality = stats_step.errors[0] if stats_step.errors else None

        except Exception as e:
            result.success = False
            logger.exception("Pipeline failed: %s", e)

        result.ended_at = datetime.utcnow().isoformat()
        result.elapsed_ms = int((time.time() - t0) * 1000)
        result.success = all(s.failed == 0 for s in result.steps) if result.steps else False
        return result

    def _run_collect(self) -> StepResult:
        step = StepResult(name="collect", started_at=datetime.utcnow().isoformat())
        try:
            collector = BilibiliCollector(self.session)
            r = collector.fetch_feed()
            step.success = r.new
            step.skipped = r.duplicate + r.skipped
            step.failed = r.failed
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_enrich(self, limit: int) -> StepResult:
        step = StepResult(name="enrich", started_at=datetime.utcnow().isoformat())
        try:
            from src.signal.enricher import ContentEnricher
            enricher = ContentEnricher(self.session)
            r = enricher.enrich_batch(limit=limit)
            step.success = r.enriched
            step.skipped = r.skipped
            step.failed = r.failed
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_extract(self, limit: int) -> StepResult:
        step = StepResult(name="extract", started_at=datetime.utcnow().isoformat())
        try:
            registry = ExtractorRegistry(self.session, self.extractors)
            r = registry.extract_all(limit=limit)
            step.success = r.extracted
            step.failed = r.failed
            step.skipped = r.skipped
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_events(self) -> StepResult:
        step = StepResult(name="build_events", started_at=datetime.utcnow().isoformat())
        try:
            builder = SignalEventBuilder(self.session)
            r = builder.build(date.today())
            step.success = r.created + r.updated
            step.errors = r.errors
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step

    def _run_stats(self) -> StepResult:
        step = StepResult(name="compute_stats", started_at=datetime.utcnow().isoformat())
        try:
            tracker = QualityTracker(self.session)
            stats = tracker.compute_stats()
            step.success = 1
            step.errors = [stats.__dict__]
        except Exception as e:
            step.failed = 1
            step.errors = [str(e)]
        step.ended_at = datetime.utcnow().isoformat()
        return step
```

- [ ] **Step 2: Write SignalScheduler**

Create `src/signal/scheduler.py`:

```python
"""Signal pipeline APScheduler integration."""
import json
import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 50


class SignalScheduler:
    def __init__(self):
        self._scheduler = None
        self._job_id = "signal_pipeline_hourly"
        self._running = False
        self._last_result = None
        self._logs: deque = deque(maxlen=MAX_LOG_ENTRIES)

    def start(self, scheduler=None):
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self._execute,
                CronTrigger(day_of_week="mon-fri", hour="9-23", minute=0),
                id=self._job_id,
                replace_existing=True,
            )
            self._scheduler.start()
        else:
            self._scheduler = scheduler
            from apscheduler.triggers.cron import CronTrigger
            self._scheduler.add_job(
                self._execute,
                CronTrigger(day_of_week="mon-fri", hour="9-23", minute=0),
                id=self._job_id,
                replace_existing=True,
            )
        self._running = True
        logger.info("Signal scheduler started")

    def stop(self):
        if self._scheduler and self._running:
            try:
                self._scheduler.remove_job(self._job_id)
            except Exception:
                pass
            self._running = False
            logger.info("Signal scheduler stopped")

    def run_now(self):
        self._execute()

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "last_result": self._last_result,
            "job_id": self._job_id,
        }

    def get_logs(self, limit: int = 50) -> list[dict]:
        return list(self._logs)[-limit:]

    def _execute(self):
        from src.storage import DatabaseManager
        from src.config import get_config

        logger.info("Signal pipeline execution started")
        start = datetime.utcnow()

        try:
            db = DatabaseManager.get_instance()
            session = db.get_session()
            config = get_config()

            from src.signal.extractor.text import TextSignalExtractor
            extractors = {
                "text": TextSignalExtractor(litellm_model=config.litellm_model),
            }

            try:
                from src.signal.extractor.video import VideoSignalExtractor
                extractors["video_subtitle"] = VideoSignalExtractor(litellm_model=config.litellm_model)
            except ImportError:
                pass
            try:
                from src.signal.extractor.image import ImageSignalExtractor
                extractors["image_text"] = ImageSignalExtractor(litellm_model=config.litellm_model)
            except ImportError:
                pass

            from src.signal.pipeline import SignalPipeline
            pipeline = SignalPipeline(session, extractors)
            result = pipeline.run()

            self._last_result = {
                "time": start.isoformat(),
                "success": result.success,
                "elapsed_ms": result.elapsed_ms,
                "steps": [
                    {"name": s.name, "success": s.success, "failed": s.failed}
                    for s in result.steps
                ],
            }
            self._logs.append(self._last_result)

            session.close()

        except Exception as e:
            logger.exception("Signal pipeline execution failed: %s", e)
            self._last_result = {
                "time": start.isoformat(),
                "success": False,
                "error": str(e),
            }
            self._logs.append(self._last_result)
```

- [ ] **Step 3: Write pipeline test**

Create `tests/signal/test_pipeline.py`:

```python
"""Tests for SignalPipeline."""
from unittest.mock import patch, MagicMock

import pytest

from src.signal.models import ContentCreator, Content
from src.signal.pipeline import SignalPipeline


class TestSignalPipeline:
    @patch("src.signal.pipeline.BilibiliCollector")
    @patch("src.signal.pipeline.ContentEnricher")
    def test_pipeline_runs_all_steps(self, mock_enricher_cls, mock_collector_cls, db_session):
        mock_collector = MagicMock()
        mock_collector.fetch_feed.return_value = MagicMock(
            new=2, duplicate=0, skipped=0, failed=0, errors=[],
        )
        mock_collector_cls.return_value = mock_collector

        mock_enricher = MagicMock()
        mock_enricher.enrich_batch.return_value = MagicMock(
            enriched=1, failed=0, skipped=1, errors=[],
        )
        mock_enricher_cls.return_value = mock_enricher

        pipeline = SignalPipeline(db_session, extractors={"text": MagicMock()})
        result = pipeline.run()

        assert len(result.steps) == 5
        assert result.steps[0].name == "collect"
        assert result.steps[1].name == "enrich"
        assert result.steps[2].name == "extract"
        assert result.steps[3].name == "build_events"
        assert result.steps[4].name == "compute_stats"
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/signal/test_pipeline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/signal/pipeline.py src/signal/scheduler.py tests/signal/test_pipeline.py
git commit -m "feat(signal): add SignalPipeline orchestrator + SignalScheduler"
```

---

## Task 10: 剩余 API 端点

**Milestone:** M2.4, M3.5, M4.4-M4.5, M5.3

**Files:**
- Create: `api/v1/endpoints/signal_content.py`
- Create: `api/v1/endpoints/signal_overview.py`
- Create: `api/v1/endpoints/signal_asset.py`
- Create: `api/v1/endpoints/signal_pipeline.py`
- Modify: `api/v1/router.py`

- [ ] **Step 1: Write Content Queue API** (`signal_content.py`)

Implement: `GET /contents` (list + filters), `GET /contents/{id}` (detail with media/transcript/mentions), `POST /contents/{id}/retry` (reset status), `POST /contents/{id}/ignore` (set ignored).

- [ ] **Step 2: Write Signal Overview API** (`signal_overview.py`)

Implement: `GET /events` (list + filters), `GET /events/{id}` (detail), `GET /stats` (top-level metrics).

- [ ] **Step 3: Write Asset Detail API** (`signal_asset.py`)

Implement: `GET /assets/{identifier}` (event + mentions summary), `GET /assets/{identifier}/mentions` (paginated), `GET /assets/{identifier}/timeline`.

- [ ] **Step 4: Write Pipeline Control API** (`signal_pipeline.py`)

Implement: `POST /pipeline/run` (trigger), `GET /pipeline/status`, `GET /pipeline/logs`.

- [ ] **Step 5: Register all new routes in `api/v1/router.py`**

Add `include_router` for `signal_content`, `signal_overview`, `signal_asset`, `signal_pipeline` with appropriate prefixes and tags.

- [ ] **Step 6: Verify compilation**

```bash
python -m py_compile api/v1/endpoints/signal_content.py
python -m py_compile api/v1/endpoints/signal_overview.py
python -m py_compile api/v1/endpoints/signal_asset.py
python -m py_compile api/v1/endpoints/signal_pipeline.py
```

- [ ] **Step 7: Commit**

```bash
git add api/v1/endpoints/signal_*.py api/v1/router.py
git commit -m "feat(signal): add Content Queue, Overview, Asset, Pipeline API endpoints"
```

---

## Task 11: 前端基础设施

**Milestone:** M1.6 准备

**Files:**
- Create: `apps/dsa-web/src/types/signal.ts`
- Create: `apps/dsa-web/src/api/signal.ts`
- Modify: `apps/dsa-web/src/App.tsx`
- Modify: `apps/dsa-web/src/components/layout/SidebarNav.tsx`

- [ ] **Step 1: Write TypeScript types**

Create `apps/dsa-web/src/types/signal.ts` with interfaces for: `Creator`, `Content`, `Mention`, `SignalEvent`, `QualityStats`, `FunnelData`, `FailureItem`, `CreatorStats`, `PipelineStatus`.

- [ ] **Step 2: Write API client**

Create `apps/dsa-web/src/api/signal.ts` using `apiClient` from `./index`, with methods for all signal endpoints. Use `toCamelCase` from `./utils` for response transformation.

- [ ] **Step 3: Add signal routes to App.tsx**

Add a `<Route>` group under `/signals` inside the `<Shell>` wrapper: `/signals`, `/signals/quality`, `/signals/content`, `/signals/asset/:identifier`, `/signals/creators`.

- [ ] **Step 4: Add signal nav items to SidebarNav**

Add a "信号" section to `NAV_ITEMS` with items for: 信号总览, 采集质量, 内容队列, UP主管理.

- [ ] **Step 5: Build to verify**

```bash
cd apps/dsa-web && npm run build
```

Expected: Build succeeds (pages can be placeholder components initially).

- [ ] **Step 6: Commit**

```bash
git add apps/dsa-web/src/types/signal.ts apps/dsa-web/src/api/signal.ts apps/dsa-web/src/App.tsx apps/dsa-web/src/components/layout/SidebarNav.tsx
git commit -m "feat(signal): add frontend types, API client, routes, and nav items"
```

---

## Task 12: 前端 — UP主管理页 + 采集质量页

**Milestone:** M1.6

**Files:**
- Create: `apps/dsa-web/src/pages/signal/CreatorManagePage.tsx`
- Create: `apps/dsa-web/src/pages/signal/QualityDashboard.tsx`
- Create: `apps/dsa-web/src/pages/signal/index.ts`

- [ ] **Step 1: Write CreatorManagePage**

Table with: name, platform, is_active toggle, category, manual_weight, last_fetch_at, notes. Actions: add (modal), edit, toggle active. Use existing Tailwind patterns from the codebase.

- [ ] **Step 2: Write QualityDashboard**

Top metrics bar (4 stats), processing funnel (horizontal bar segments), UP主 status table, failure reasons ranked list. Time range selector.

- [ ] **Step 3: Write barrel export**

Create `apps/dsa-web/src/pages/signal/index.ts`:

```typescript
export { default as SignalOverviewPage } from './SignalOverviewPage';
export { default as QualityDashboard } from './QualityDashboard';
export { default as ContentQueuePage } from './ContentQueuePage';
export { default as AssetDetailPage } from './AssetDetailPage';
export { default as CreatorManagePage } from './CreatorManagePage';
```

- [ ] **Step 4: Build and verify**

```bash
cd apps/dsa-web && npm run lint && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/pages/signal/
git commit -m "feat(signal): add Creator management + Quality dashboard pages"
```

---

## Task 13: 前端 — 内容队列 + 信号总览 + 标的详情

**Milestone:** M2.5, M3.6, M4.6

**Files:**
- Create: `apps/dsa-web/src/pages/signal/ContentQueuePage.tsx`
- Create: `apps/dsa-web/src/pages/signal/SignalOverviewPage.tsx`
- Create: `apps/dsa-web/src/pages/signal/AssetDetailPage.tsx`

- [ ] **Step 1: Write ContentQueuePage**

Filterable table (status, display_type, creator). Row actions: view original (external link), retry, ignore. Status badges with colors.

- [ ] **Step 2: Write SignalOverviewPage**

Top 4 metrics. Event type tabs (opportunity/risk/conflict/watch). Event card list: asset name, type badge, score, creator count, top creator. Click → navigate to asset detail.

- [ ] **Step 3: Write AssetDetailPage**

Header: asset info + event type badge + bullish/bearish ratio bar. Mention cards: creator name + weight, title, time, sentiment, confidence, reasoning (expandable), trade_advice, key_levels, quality flags, source link.

- [ ] **Step 4: Build and verify**

```bash
cd apps/dsa-web && npm run lint && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/pages/signal/
git commit -m "feat(signal): add Content Queue, Signal Overview, Asset Detail pages"
```

---

## Task 14: Uploaders 迁移 + 最终集成

**Milestone:** M1.7, M5.4-M5.5

**Files:**
- Create: `scripts/migrate_uploaders.py`
- Modify: `src/signal/__init__.py` — add ensure_tables call
- Verify: full integration

- [ ] **Step 1: Write uploaders migration script**

Create `scripts/migrate_uploaders.py`:

```python
"""Migrate config/uploaders.json → content_creators table."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage import DatabaseManager
from src.signal.models import ContentCreator, ensure_signal_tables


def migrate():
    uploaders_path = Path("config/uploaders.json")
    if not uploaders_path.exists():
        print("config/uploaders.json not found")
        return

    with open(uploaders_path) as f:
        data = json.load(f)

    db = DatabaseManager.get_instance()
    ensure_signal_tables(db._engine)
    session = db.get_session()

    count = 0
    for group_key in ["key_uploaders", "filter_uploaders"]:
        for entry in data.get(group_key, []):
            uid = str(entry.get("uid", ""))
            if not uid:
                continue

            existing = session.query(ContentCreator).filter_by(
                platform="bilibili", platform_uid=uid,
            ).first()
            if existing:
                continue

            priority = entry.get("priority", 2)
            weight_map = {1: 1.5, 2: 1.0, 3: 0.7}

            creator = ContentCreator(
                platform="bilibili",
                platform_uid=uid,
                name=entry.get("name", f"uid_{uid}"),
                category=entry.get("category", ""),
                is_active=entry.get("is_active", True),
                manual_weight=weight_map.get(priority, 1.0),
                fetch_interval_min=entry.get("fetch_interval_min", 60),
            )
            session.add(creator)
            count += 1

    session.commit()
    session.close()
    print(f"Migrated {count} creators")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: Add table initialization to signal __init__**

Update `src/signal/__init__.py` — add a function that ensures tables exist when the module is first used by API:

```python
def init_signal_db():
    """Call during app startup to ensure signal tables exist."""
    from src.storage import DatabaseManager
    try:
        db = DatabaseManager.get_instance()
        ensure_signal_tables(db._engine)
    except Exception:
        pass
```

- [ ] **Step 3: Call init_signal_db in app startup**

Add to `api/app.py` inside `create_app()`, after router is included:

```python
from src.signal import init_signal_db
init_signal_db()
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/signal/ -v
```

Expected: All PASS.

- [ ] **Step 5: Verify backend compilation**

```bash
python -m py_compile src/signal/models.py
python -m py_compile src/signal/collector.py
python -m py_compile src/signal/quality.py
python -m py_compile src/signal/event_builder.py
python -m py_compile src/signal/pipeline.py
python -m py_compile src/signal/scheduler.py
```

- [ ] **Step 6: Verify frontend build**

```bash
cd apps/dsa-web && npm run lint && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add scripts/migrate_uploaders.py src/signal/__init__.py api/app.py
git commit -m "feat(signal): add uploaders migration + app integration + table init"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Task |
| --- | --- |
| §4 Data Models (6 tables) | Task 1 |
| §5.2 BilibiliCollector | Task 2 |
| §5.2 QualityTracker | Task 3 |
| §5.2 Extractors | Task 6, 7 |
| §5.2 ContentEnricher | Task 8 |
| §5.2 SignalEventBuilder | Task 5 |
| §5.2 SignalPipeline + Scheduler | Task 9 |
| §6.1-6.6 API endpoints | Task 4, 10 |
| §7.1-7.5 Frontend pages | Task 11, 12, 13 |
| §8 Scheduler integration | Task 9 |
| §9 M1-M5 milestones | Tasks 1-14 cover all |
| §12 System boundary (init_signal_db) | Task 14 |

### Placeholder Scan

No TBD, TODO, or "implement later" in any task. Tasks 7, 8, 10, 11, 12, 13 have less code detail than Tasks 1-6 but provide clear implementation instructions with file paths and behavior specs. These tasks follow established patterns from earlier tasks.

### Type Consistency

- `CollectResult` — defined in `collector.py`, consumed in `pipeline.py`
- `ExtractResult` — defined in `extractor/base.py`, consumed in `registry.py` and `pipeline.py`
- `EventBuildResult` — defined in `event_builder.py`, consumed in `pipeline.py`
- `QualityStats` — defined in `quality.py`, consumed in API
- `MentionData` — defined in `extractor/base.py`, consumed in all extractors and registry
- `PipelineResult` / `StepResult` — defined in `pipeline.py`, consumed in `scheduler.py` and API
- All Pydantic schemas in `api/v1/schemas/signal.py` match the ORM model field names
