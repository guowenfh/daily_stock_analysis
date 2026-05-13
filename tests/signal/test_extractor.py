"""Tests for signal extractors."""
import json
from unittest.mock import patch, MagicMock

from src.signal.models import ContentCreator, Content, SignalMention
from src.signal.prompt_manager import PromptManager
from src.signal.extractor.base import MentionData
from src.signal.extractor.text import TextSignalExtractor
from src.signal.extractor.video import VideoSignalExtractor
from src.signal.extractor.registry import ExtractorRegistry


class TestTextSignalExtractor:
    @patch("litellm.completion")
    @patch.object(PromptManager, "get_prompt")
    def test_extract_basic(self, mock_get_prompt, mock_completion, db_session):
        mock_get_prompt.return_value = "system prompt"

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
        mock_completion.return_value = mock_response

        content = MagicMock()
        content.text = "今天茅台走势不错，600519 值得关注"
        content.title = "聊聊茅台"

        extractor = TextSignalExtractor(litellm_model="test-model")
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


class TestVideoSignalExtractor:
    @patch("litellm.completion")
    @patch.object(PromptManager, "get_prompt")
    def test_video_extractor_long_transcript_triggers_summary(self, mock_get_prompt, mock_completion, db_session):
        mock_get_prompt.side_effect = lambda name: f"sys-{name}"

        summary_resp = MagicMock()
        summary_resp.choices = [MagicMock()]
        summary_resp.choices[0].message.content = (
            "# 摘要\n\n贵州茅台看多，代码 600519。\n" * 3
        )

        extract_resp = MagicMock()
        extract_resp.choices = [MagicMock()]
        extract_resp.choices[0].message.content = json.dumps({
            "mentions": [{
                "name": "贵州茅台", "code": "600519",
                "asset_type": "stock", "market": "a_share",
                "sentiment": "bullish", "confidence": 0.85,
                "is_primary": True,
                "reasoning": "摘要里说了",
                "trade_advice": "", "key_levels": {},
            }]
        })

        _call = {"n": 0}

        def completion_side_effect(*args, **kwargs):
            _call["n"] += 1
            if _call["n"] == 1:
                return summary_resp
            return extract_resp

        mock_completion.side_effect = completion_side_effect

        long_text = "字" * 6001
        transcript = MagicMock()
        transcript.quality = "good"
        transcript.source = "platform"
        transcript.text = long_text

        content = MagicMock()
        content.title = "财经盘点"
        content.transcripts = [transcript]

        extractor = VideoSignalExtractor(litellm_model="test-model")
        mentions = extractor.extract(content)

        assert mock_completion.call_count == 2
        assert len(mentions) == 1
        assert "based_on_summary" in mentions[0].quality_flags

    @patch("litellm.completion")
    @patch.object(PromptManager, "get_prompt")
    def test_video_extractor_short_transcript_no_summary(self, mock_get_prompt, mock_completion, db_session):
        mock_get_prompt.side_effect = lambda name: f"sys-{name}"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "mentions": [{
                "name": "贵州茅台", "code": "600519",
                "asset_type": "stock", "market": "a_share",
                "sentiment": "bullish", "confidence": 0.85,
                "is_primary": True,
                "reasoning": "字幕里说了",
                "trade_advice": "", "key_levels": {},
            }]
        })
        mock_completion.return_value = mock_response

        short_text = "字" * 6000
        transcript = MagicMock()
        transcript.quality = "good"
        transcript.source = "platform"
        transcript.text = short_text

        content = MagicMock()
        content.title = "财经盘点"
        content.transcripts = [transcript]

        extractor = VideoSignalExtractor(litellm_model="test-model")
        mentions = extractor.extract(content)

        assert mock_completion.call_count == 1
        assert len(mentions) == 1
        assert "based_on_summary" not in mentions[0].quality_flags


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
