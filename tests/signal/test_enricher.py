"""Tests for ContentEnricher."""
from unittest.mock import patch, MagicMock

from src.signal.models import ContentCreator, Content, ContentMedia, ContentTranscript
from src.signal.enricher import ContentEnricher


class TestContentEnricher:
    def _setup_creator(self, session):
        c = ContentCreator(platform="bilibili", platform_uid="1", name="UP1")
        session.add(c)
        session.flush()
        return c

    def _setup_video_content(self, session, creator, bvid="BV1test"):
        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id=bvid,
            content_type="video",
            display_type="video_subtitle",
            title="测试视频",
            status="pending_enrich",
        )
        session.add(content)
        session.flush()
        return content

    @patch("src.signal.enricher.subprocess.run")
    def test_video_platform_subtitle(self, mock_run, db_session):
        creator = self._setup_creator(db_session)
        content = self._setup_video_content(db_session, creator)
        db_session.commit()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                'subtitle: "这是一段足够长的字幕内容，用来测试平台字幕获取功能是否正常工作，'
                '需要超过五十个字符才能标记为good"'
            ),
        )

        enricher = ContentEnricher(db_session)
        result = enricher.enrich_batch()

        assert result.enriched == 1
        assert content.status == "pending_extract"
        transcript = db_session.query(ContentTranscript).first()
        assert transcript is not None
        assert transcript.quality == "good"

    @patch("src.signal.enricher.subprocess.run")
    def test_video_no_subtitle_title_only(self, mock_run, db_session):
        creator = self._setup_creator(db_session)
        content = self._setup_video_content(db_session, creator)
        db_session.commit()

        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )

        enricher = ContentEnricher(db_session)
        result = enricher.enrich_batch()

        assert result.enriched == 1
        transcript = db_session.query(ContentTranscript).first()
        assert transcript.quality == "title_only"

    @patch("litellm.completion")
    @patch("src.config.get_config")
    def test_image_enrichment(self, mock_get_config, mock_completion, db_session):
        creator = self._setup_creator(db_session)
        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id="img_1",
            content_type="image",
            display_type="image_text",
            title="图文测试",
            status="pending_enrich",
        )
        db_session.add(content)
        db_session.flush()

        media = ContentMedia(
            content_id=content.id,
            media_type="image",
            url="https://example.com/img.jpg",
        )
        db_session.add(media)
        db_session.commit()

        mock_get_config.return_value = MagicMock(litellm_model="test-model")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "K线显示上涨趋势"
        mock_completion.return_value = mock_response

        enricher = ContentEnricher(db_session)
        result = enricher.enrich_batch()

        assert result.enriched == 1
        assert content.status == "pending_extract"
        assert media.ocr_text == "K线显示上涨趋势"

    @patch("src.signal.enricher.subprocess.run")
    def test_failure_handling(self, mock_run, db_session):
        creator = self._setup_creator(db_session)
        content = self._setup_video_content(db_session, creator)
        db_session.commit()

        mock_run.side_effect = Exception("CLI crashed")

        enricher = ContentEnricher(db_session)
        result = enricher.enrich_batch()

        assert result.failed == 1
        assert content.status == "failed"
        assert content.failure_stage == "enrich"
