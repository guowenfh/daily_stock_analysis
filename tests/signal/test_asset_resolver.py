"""Tests for AssetResolver stock index enrichment."""
from unittest.mock import patch

import pytest

from src.signal.asset_resolver import AssetResolver, _guess_market
from src.signal.extractor.base import MentionData


@pytest.fixture
def sample_index_map():
    return {
        "600519": "贵州茅台",
        "600519.SH": "贵州茅台",
        "000001": "平安银行",
        "601318": "中国平安",
        "00700": "腾讯控股",
        "00700.HK": "腾讯控股",
        "AAPL": "苹果",
    }


class TestGuessMarket:
    def test_guess_a_share_suffix(self):
        assert _guess_market("600519.SH") == "a_share"

    def test_guess_hk(self):
        assert _guess_market("00700.HK") == "hk"

    def test_guess_us(self):
        assert _guess_market("AAPL") == "us"


@patch("src.signal.asset_resolver.get_stock_name_index_map")
class TestAssetResolver:
    def test_resolve_by_code_exact(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="茅台", code="600519")
        r = AssetResolver()
        out = r.resolve([m])
        assert out[0].code == "600519"
        assert out[0].market == "a_share"
        assert out[0].name == "贵州茅台"

    def test_resolve_code_not_found(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="irrelevant_xyz", code="999999")
        r = AssetResolver()
        r.resolve([m])
        assert m.code == "999999"
        assert "code_unresolved" in m.quality_flags

    def test_resolve_by_name_exact(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="贵州茅台", code=None)
        r = AssetResolver()
        r.resolve([m])
        assert m.code == "600519"
        assert m.market == "a_share"

    def test_resolve_by_name_prefix(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="茅台", code=None)
        r = AssetResolver()
        r.resolve([m])
        assert m.code == "600519"
        assert m.name == "贵州茅台"

    def test_resolve_no_match(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="不是任何股票", code=None)
        r = AssetResolver()
        r.resolve([m])
        assert m.code is None
        assert "code_unresolved" in m.quality_flags

    def test_resolve_us_stock(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="苹果", code="AAPL")
        r = AssetResolver()
        r.resolve([m])
        assert m.market == "us"
        assert m.code == "AAPL"

    def test_resolve_hk_stock(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="腾讯", code="00700")
        r = AssetResolver()
        r.resolve([m])
        assert m.market == "hk"
        assert m.code == "00700"

    def test_resolve_multiple_matches_ambiguous(self, mock_index, sample_index_map):
        mock_index.return_value = sample_index_map
        m = MentionData(name="平安", code=None)
        r = AssetResolver()
        r.resolve([m])
        assert "name_ambiguous" in m.quality_flags
        assert "code_unresolved" in m.quality_flags
        assert m.code is None
