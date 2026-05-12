"""Tests for signal data models."""
from datetime import datetime, date

import pytest

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
