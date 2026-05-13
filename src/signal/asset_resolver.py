# -*- coding: utf-8 -*-
"""Resolve and enrich signal mentions using the generated stock index."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.data.stock_index_loader import _build_lookup_keys, get_stock_name_index_map
from src.signal.extractor.base import MentionData


def _guess_market(code: str) -> str:
    """Infer market from a ticker string."""
    c = str(code or "").strip().upper()
    if not c:
        return "unknown"
    if c.startswith("HK") and len(c) > 2 and c[2:].isdigit():
        return "hk"
    if "." in c:
        _base, suf = c.rsplit(".", 1)
        if suf in {"SH", "SZ", "BJ"}:
            return "a_share"
        if suf == "HK":
            return "hk"
    if c.isdigit():
        if len(c) == 6:
            return "a_share"
        if 1 <= len(c) <= 5:
            return "hk"
    if c.isalpha() and 1 <= len(c) <= 5:
        return "us"
    return "unknown"


def _bucket_id(code: str) -> Optional[str]:
    """Stable bucket for de-duplicating index keys that refer to the same security."""
    c0 = str(code or "").strip()
    if not c0:
        return None
    c = c0.upper()
    if c.startswith("HK") and len(c) > 2 and c[2:].isdigit():
        return f"hk:{c[2:].zfill(5)}"
    if "." in c:
        base, suf = c.rsplit(".", 1)
        if suf in {"SH", "SZ", "BJ"} and base.isdigit():
            return f"a:{base.zfill(6)}"
        if suf == "HK" and base.isdigit():
            return f"hk:{base.zfill(5)}"
    if c.isdigit():
        if len(c) == 6:
            return f"a:{c}"
        if 1 <= len(c) <= 5:
            return f"hk:{c.zfill(5)}"
    if c.isalpha() and 1 <= len(c) <= 5:
        return f"us:{c}"
    return f"raw:{c}"


def _preferred_display_code(code_key: str) -> str:
    """Normalize display code for a resolved security."""
    c0 = str(code_key or "").strip()
    if not c0:
        return ""
    c = c0.upper()
    bid = _bucket_id(c0) or f"raw:{c}"
    kind, _, rest = bid.partition(":")
    if kind == "a":
        return rest
    if kind == "hk":
        return rest.zfill(5)
    if kind == "us":
        return rest
    return c0.strip()


def _add_flag(mention: MentionData, flag: str) -> None:
    if flag not in mention.quality_flags:
        mention.quality_flags.append(flag)


def _remove_flag(mention: MentionData, flag: str) -> None:
    if flag in mention.quality_flags:
        mention.quality_flags = [f for f in mention.quality_flags if f != flag]


class AssetResolver:
    """Match mentions to `stocks.index.json` entries and fill code / market metadata."""

    def __init__(self, forward_map: Optional[Dict[str, str]] = None) -> None:
        self._forward: Dict[str, str] = (
            dict(forward_map) if forward_map is not None else get_stock_name_index_map()
        )
        # name_zh -> bucket_id -> preferred display code
        self._name_buckets: Dict[str, Dict[str, str]] = {}
        self._build_name_index()

    def _build_name_index(self) -> None:
        for key, zh_name in self._forward.items():
            name = str(zh_name or "").strip()
            if not name:
                continue
            bid = _bucket_id(key)
            if not bid:
                continue
            code = _preferred_display_code(key)
            self._name_buckets.setdefault(name, {})[bid] = code

    def _lookup_code_name(self, code: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (preferred_code, zh_name) if `code` matches the index."""
        for key in _build_lookup_keys(code, code):
            zh_name = self._forward.get(key)
            if zh_name:
                return _preferred_display_code(key), str(zh_name).strip()
        return None, None

    def _candidate_names(self, mention_name: str) -> List[str]:
        mn = str(mention_name or "").strip()
        if not mn:
            return []
        if mn in self._name_buckets:
            return [mn]
        return [n for n in self._name_buckets if n.startswith(mn) or n.endswith(mn)]

    def _union_buckets_for_names(self, names: List[str]) -> Dict[str, str]:
        union: Dict[str, str] = {}
        for n in names:
            union.update(self._name_buckets.get(n, {}))
        return union

    def _resolve_one(self, mention: MentionData) -> None:
        _remove_flag(mention, "name_ambiguous")

        code_str = str(mention.code).strip() if mention.code else ""
        resolved_code: Optional[str] = None
        resolved_name: Optional[str] = None

        if code_str:
            pref_code, zh_name = self._lookup_code_name(code_str)
            if pref_code and zh_name:
                resolved_code = pref_code
                resolved_name = zh_name

        if not resolved_code:
            hits = self._candidate_names(mention.name)
            union = self._union_buckets_for_names(hits)
            if len(union) > 1:
                _add_flag(mention, "name_ambiguous")
            elif len(union) == 1:
                resolved_code = next(iter(union.values()))
                if len(hits) == 1:
                    resolved_name = hits[0]
                else:
                    _, zn = self._lookup_code_name(resolved_code)
                    resolved_name = zn

        if resolved_code:
            mention.code = resolved_code
            if resolved_name:
                mention.name = str(resolved_name).strip()
            mention.market = _guess_market(resolved_code)
            _remove_flag(mention, "code_unresolved")
            return

        _add_flag(mention, "code_unresolved")

    def resolve(self, mentions: List[MentionData]) -> List[MentionData]:
        for m in mentions:
            self._resolve_one(m)
        return mentions
