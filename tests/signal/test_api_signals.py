# -*- coding: utf-8 -*-
"""Integration tests for signal overview and asset API endpoints."""
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import Config
from src.signal.models import (
    Content,
    ContentCreator,
    ContentTranscript,
    SignalEvent,
    SignalMention,
    ensure_signal_tables,
)
from src.storage import DatabaseManager


@pytest.fixture
def client():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "signal_api_test.db"
        os.environ["DATABASE_PATH"] = str(db_path)

        db_manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
        ensure_signal_tables(db_manager._engine)

        from api.app import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c

    DatabaseManager.reset_instance()
    Config.reset_instance()


def _seed_data(client):
    """Seed a creator, content, mention, and event for tests."""
    from src.storage import DatabaseManager

    session = DatabaseManager.get_instance().get_session()

    creator = ContentCreator(
        platform="bilibili", platform_uid="seed1", name="种子UP主"
    )
    session.add(creator)
    session.flush()

    content = Content(
        creator_id=creator.id,
        platform="bilibili",
        platform_content_id="vid001",
        content_type="video",
        display_type="video",
        title="测试视频",
        text="测试正文内容",
        status="extracted",
    )
    session.add(content)
    session.flush()

    transcript = ContentTranscript(
        content_id=content.id, source="whisper", quality="good", text="字幕原文"
    )
    session.add(transcript)
    session.flush()

    mention = SignalMention(
        content_id=content.id,
        creator_id=creator.id,
        asset_name="贵州茅台",
        asset_code="600519",
        asset_type="stock",
        market="A",
        sentiment="bullish",
        confidence=0.85,
        is_primary=True,
        reasoning="看好白酒",
    )
    session.add(mention)
    session.flush()

    event = SignalEvent(
        asset_name="贵州茅台",
        asset_code="600519",
        asset_type="stock",
        market="A",
        event_type="opportunity",
        event_date=date.today(),
        score=3.5,
        bullish_count=1,
        bearish_count=0,
        neutral_count=0,
        creator_count=1,
        mention_count=1,
        top_creator_name="种子UP主",
    )
    session.add(event)
    session.commit()
    return {
        "creator": creator,
        "content": content,
        "mention": mention,
        "event": event,
    }


class TestEventsSortAPI:
    def test_default_sort_by_score(self, client):
        _seed_data(client)
        resp = client.get("/api/v1/signals/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["score"] == 3.5

    def test_sort_by_created_at_asc(self, client):
        _seed_data(client)
        resp = client.get(
            "/api/v1/signals/events",
            params={"sort_by": "created_at", "sort_order": "asc"},
        )
        assert resp.status_code == 200

    def test_sort_by_mention_count(self, client):
        _seed_data(client)
        resp = client.get(
            "/api/v1/signals/events",
            params={"sort_by": "mention_count", "sort_order": "desc"},
        )
        assert resp.status_code == 200
        assert resp.json()[0]["mention_count"] == 1

    def test_invalid_sort_by_returns_422(self, client):
        resp = client.get(
            "/api/v1/signals/events", params={"sort_by": "invalid_field"}
        )
        assert resp.status_code == 422

    def test_invalid_sort_order_returns_422(self, client):
        resp = client.get(
            "/api/v1/signals/events", params={"sort_order": "invalid"}
        )
        assert resp.status_code == 422

    def test_event_type_filter(self, client):
        _seed_data(client)
        resp = client.get(
            "/api/v1/signals/events", params={"event_type": "opportunity"}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = client.get(
            "/api/v1/signals/events", params={"event_type": "risk"}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestMentionsIncludeContentAPI:
    def test_mentions_without_content(self, client):
        _seed_data(client)
        resp = client.get("/api/v1/signals/assets/600519/mentions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["content_text"] is None
        assert data[0]["transcript_text"] is None
        assert data[0]["summary_text"] is None

    def test_mentions_with_content(self, client):
        _seed_data(client)
        resp = client.get(
            "/api/v1/signals/assets/600519/mentions",
            params={"include_content": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["content_text"] == "测试正文内容"
        assert data[0]["transcript_text"] == "字幕原文"
        assert data[0]["summary_text"] is None

    def test_mentions_by_name(self, client):
        _seed_data(client)
        resp = client.get(
            "/api/v1/signals/assets/%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0/mentions"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestOverviewStatsAPI:
    def test_stats_include_signal_counts(self, client):
        _seed_data(client)
        resp = client.get("/api/v1/signals/stats", params={"days": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert "signal_mention_count" in data
        assert "signal_event_count" in data
        assert data["signal_mention_count"] >= 1
        assert data["signal_event_count"] >= 1

    def test_stats_empty_db(self, client):
        resp = client.get("/api/v1/signals/stats", params={"days": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal_mention_count"] == 0
        assert data["signal_event_count"] == 0
        assert data["total_contents"] == 0
