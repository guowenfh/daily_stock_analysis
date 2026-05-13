"""Tests for QualityTracker."""
from datetime import date, datetime

import pytest

from src.signal.models import ContentCreator, Content, SignalEvent, SignalMention
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

    def test_signal_counts(self, db_session):
        c = self._add_creator(db_session)
        content = self._add_content(db_session, c.id, "p1", status="extracted")

        mention = SignalMention(
            content_id=content.id, creator_id=c.id,
            asset_name="贵州茅台", asset_code="600519",
            asset_type="stock", market="A",
            sentiment="bullish", confidence=0.9,
        )
        db_session.add(mention)
        db_session.flush()

        event = SignalEvent(
            asset_name="贵州茅台", asset_code="600519",
            asset_type="stock", market="A",
            event_type="opportunity", event_date=date.today(),
            score=3.0, mention_count=1, creator_count=1,
        )
        db_session.add(event)
        db_session.commit()

        tracker = QualityTracker(db_session)
        stats = tracker.compute_stats(since=datetime(2020, 1, 1))
        assert stats.signal_mention_count == 1
        assert stats.signal_event_count == 1

    def test_signal_counts_zero_when_empty(self, db_session):
        tracker = QualityTracker(db_session)
        stats = tracker.compute_stats(since=datetime(2020, 1, 1))
        assert stats.signal_mention_count == 0
        assert stats.signal_event_count == 0
