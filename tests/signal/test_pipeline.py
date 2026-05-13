"""Tests for SignalPipeline."""
from unittest.mock import MagicMock, patch

from src.signal.models import ContentCreator, Content, SignalMention
from src.signal.extractor.registry import ExtractorRegistry
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


def test_idempotent_extract_skips_existing_mentions(db_session):
    """已有 mentions 的 pending_extract 内容应跳过，不重复提取。"""
    creator = ContentCreator(platform="bilibili", platform_uid="123", name="测试UP主")
    db_session.add(creator)
    db_session.flush()

    content = Content(
        creator_id=creator.id,
        platform="bilibili",
        platform_content_id="test_idem_001",
        content_type="dynamic",
        display_type="text",
        title="测试内容",
        status="pending_extract",
    )
    db_session.add(content)
    db_session.flush()

    existing_mention = SignalMention(
        content_id=content.id,
        creator_id=creator.id,
        asset_name="贵州茅台",
        asset_type="stock",
        sentiment="bullish",
        confidence=0.8,
    )
    db_session.add(existing_mention)
    db_session.commit()

    class DummyExtractor:
        def extract(self, c):
            raise AssertionError("Should not be called for already-extracted content")

    registry = ExtractorRegistry(db_session, {"text": DummyExtractor()})
    result = registry.extract_all()

    assert result.skipped == 1
    assert result.extracted == 0
    assert content.status == "extracted"
