"""Tests for SignalEventBuilder."""
from datetime import date, datetime, timezone

from src.signal.models import ContentCreator, Content, SignalMention, SignalEvent
from src.signal.event_builder import SignalEventBuilder


def _event_build_date() -> date:
    """Match SignalMention.created_at (utcnow) calendar day for filtering."""
    return datetime.now(timezone.utc).date()


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
        result = builder.build(_event_build_date())

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
        builder.build(_event_build_date())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "conflict"

    def test_risk_event(self, db_session):
        self._setup(db_session, n_creators=3,
                     sentiments=["bearish", "bearish", "bearish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        builder.build(_event_build_date())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "risk"

    def test_watch_event_single_mention(self, db_session):
        self._setup(db_session, n_creators=1, sentiments=["bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        builder.build(_event_build_date())

        event = db_session.query(SignalEvent).first()
        assert event.event_type == "watch"

    def test_evidence_populated(self, db_session):
        self._setup(db_session, n_creators=2, sentiments=["bullish", "bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        builder.build(_event_build_date())

        event = db_session.query(SignalEvent).first()
        evidence = event.get_evidence()
        assert len(evidence) == 2
        assert evidence[0]["sentiment"] == "bullish"
        assert "creator_name" in evidence[0]

    def test_update_existing_event(self, db_session):
        self._setup(db_session, n_creators=2, sentiments=["bullish", "bullish"])
        db_session.commit()

        builder = SignalEventBuilder(db_session)
        r1 = builder.build(_event_build_date())
        assert r1.created == 1

        r2 = builder.build(_event_build_date())
        assert r2.updated == 1
        assert db_session.query(SignalEvent).count() == 1
