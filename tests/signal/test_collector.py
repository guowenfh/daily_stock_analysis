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
