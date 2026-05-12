"""Tests for SignalPipeline."""
from unittest.mock import MagicMock, patch

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
