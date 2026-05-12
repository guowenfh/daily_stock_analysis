"""Tests for signal extractors."""
import json
from unittest.mock import patch, MagicMock

from src.signal.models import ContentCreator, Content, SignalMention
from src.signal.prompt_manager import PromptManager
from src.signal.extractor.base import MentionData
from src.signal.extractor.text import TextSignalExtractor
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
