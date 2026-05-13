# 信号系统 V1 迭代 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有信号系统 V1 基础上，新增长字幕 2-pass LLM、标的字典校验、全链路幂等，并将前端从 5 页面重构为简报流 + 研究态侧边栏 + 设置区。

**Architecture:** 后端在现有 `src/signal/` 骨架上精准插入变更：VideoSignalExtractor 新增摘要分支，新建 AssetResolver 模块由 ExtractorRegistry 调用，提取前加幂等检查。前端新建 SignalBriefingPage（Tab + 侧边栏）和 SignalSettingsPage，复用现有子组件。

**Tech Stack:** Python 3.12 / SQLAlchemy / LiteLLM / FastAPI / React / TypeScript / Tailwind CSS / Lucide / Recharts

**Spec:** `docs/superpowers/specs/2026-05-13-signal-system-v1-iteration-design.md`

---

## 文件结构

### 新建文件

| 文件 | 职责 |
| --- | --- |
| `src/signal/asset_resolver.py` | 标的字典校验：加载 stocks.index.json，按 code/name 匹配填充 MentionData |
| `config/prompts/signal_video_summary.yaml` | 长字幕摘要 prompt 模板 |
| `tests/signal/test_asset_resolver.py` | AssetResolver 测试 |
| `apps/dsa-web/src/pages/signal/SignalBriefingPage.tsx` | 简报流主视图 |
| `apps/dsa-web/src/pages/signal/SignalSettingsPage.tsx` | 设置区（Tab 容器） |
| `apps/dsa-web/src/components/signal/ResearchSidebar.tsx` | 研究态侧边栏 |
| `apps/dsa-web/src/components/signal/EventCard.tsx` | 事件卡片组件 |
| `apps/dsa-web/src/components/signal/StatusBar.tsx` | 状态条组件 |
| `apps/dsa-web/src/components/signal/CreatorTimeline.tsx` | UP 主动态时间线组件 |
| `apps/dsa-web/src/components/signal/ContentViewer.tsx` | 原文/摘要内联查看组件 |

### 修改文件

| 文件 | 变更 |
| --- | --- |
| `src/signal/extractor/video.py` | 2-pass LLM：摘要 + 提取 + based_on_summary 标记 |
| `src/signal/extractor/registry.py` | 集成 AssetResolver + 提取前幂等检查 |
| `api/v1/endpoints/signal_overview.py` | sort_by / sort_order 查询参数 |
| `api/v1/endpoints/signal_asset.py` | include_content 查询参数 |
| `api/v1/schemas/signal.py` | MentionResponse 扩展字段 |
| `tests/signal/test_extractor.py` | 2-pass LLM 测试用例 |
| `tests/signal/test_pipeline.py` | 幂等性测试用例 |
| `apps/dsa-web/src/App.tsx` | 路由变更 |
| `apps/dsa-web/src/components/layout/SidebarNav.tsx` | 导航变更 |
| `apps/dsa-web/src/api/signal.ts` | 新参数 + 新响应类型 |
| `apps/dsa-web/src/types/signal.ts` | 新类型定义 |
| `apps/dsa-web/src/pages/signal/index.ts` | 导出变更 |

---

## Task 1: AssetResolver 标的字典校验

**Files:**
- Create: `src/signal/asset_resolver.py`
- Create: `tests/signal/test_asset_resolver.py`
- Reference: `src/data/stock_index_loader.py` (复用其加载逻辑)

- [ ] **Step 1: Write the failing test — code 精确匹配**

```python
# tests/signal/test_asset_resolver.py
import pytest
from unittest.mock import patch
from src.signal.asset_resolver import AssetResolver
from src.signal.extractor.base import MentionData


@pytest.fixture
def mock_index():
    """Mock stock index: {code: name} mapping."""
    return {
        "600519": "贵州茅台",
        "600519.SH": "贵州茅台",
        "000001": "平安银行",
        "000001.SZ": "平安银行",
        "AAPL": "苹果",
        "00700": "腾讯控股",
        "HK00700": "腾讯控股",
    }


@pytest.fixture
def resolver(mock_index):
    with patch("src.signal.asset_resolver.get_stock_name_index_map", return_value=mock_index):
        return AssetResolver()


def test_resolve_by_code_exact(resolver):
    mentions = [MentionData(name="茅台", code="600519")]
    result = resolver.resolve(mentions)
    assert result[0].code == "600519"
    assert result[0].market != "unknown"
    assert "code_unresolved" not in result[0].quality_flags


def test_resolve_code_not_found(resolver):
    mentions = [MentionData(name="某某公司", code="999999")]
    result = resolver.resolve(mentions)
    assert "code_unresolved" in result[0].quality_flags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/signal/test_asset_resolver.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.signal.asset_resolver'"

- [ ] **Step 3: Write AssetResolver implementation**

```python
# src/signal/asset_resolver.py
"""Resolve asset codes and markets using the stock index."""
import logging
from typing import Optional

from src.data.stock_index_loader import get_stock_name_index_map

logger = logging.getLogger(__name__)


# code → market heuristic
def _guess_market(code: str) -> str:
    code_upper = code.upper().strip()
    if code_upper.endswith(".SH") or code_upper.endswith(".SZ") or code_upper.endswith(".BJ"):
        return "a_share"
    if code_upper.endswith(".HK") or code_upper.startswith("HK"):
        return "hk"
    if code_upper.isdigit():
        if len(code_upper) == 6:
            return "a_share"
        if 1 <= len(code_upper) <= 5:
            return "hk"
    if code_upper.isalpha() and len(code_upper) <= 5:
        return "us"
    return "unknown"


class AssetResolver:
    def __init__(self):
        self._code_to_name = get_stock_name_index_map()
        self._name_to_codes: dict[str, list[str]] = {}
        self._build_name_index()

    def _build_name_index(self):
        seen_names: dict[str, set[str]] = {}
        for code, name in self._code_to_name.items():
            name_lower = name.strip()
            if name_lower not in seen_names:
                seen_names[name_lower] = set()
            seen_names[name_lower].add(code)
        for name, codes in seen_names.items():
            self._name_to_codes[name] = sorted(codes)

    def resolve(self, mentions: list) -> list:
        for m in mentions:
            self._resolve_one(m)
        return mentions

    def _resolve_one(self, mention) -> None:
        if mention.code:
            resolved_name = self._match_by_code(mention.code)
            if resolved_name:
                mention.market = _guess_market(mention.code)
                return

        codes = self._match_by_name(mention.name)
        if codes and len(codes) == 1:
            canonical = codes[0]
            mention.code = canonical.split(".")[0] if "." in canonical else canonical
            mention.market = _guess_market(canonical)
            if "code_unresolved" in mention.quality_flags:
                mention.quality_flags.remove("code_unresolved")
        elif codes and len(codes) > 1:
            if "name_ambiguous" not in mention.quality_flags:
                mention.quality_flags.append("name_ambiguous")

    def _match_by_code(self, code: str) -> Optional[str]:
        code = code.strip()
        for key in (code, code.upper()):
            name = self._code_to_name.get(key)
            if name:
                return name
        return None

    def _match_by_name(self, name: str) -> Optional[list[str]]:
        name = name.strip()
        if name in self._name_to_codes:
            return self._name_to_codes[name]
        for idx_name, codes in self._name_to_codes.items():
            if idx_name.startswith(name) or name.startswith(idx_name):
                return codes
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/signal/test_asset_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Write additional tests — name 匹配 + 前缀匹配**

```python
# 追加到 tests/signal/test_asset_resolver.py

def test_resolve_by_name_exact(resolver):
    mentions = [MentionData(name="贵州茅台")]
    result = resolver.resolve(mentions)
    assert result[0].code is not None
    assert result[0].market == "a_share"


def test_resolve_by_name_prefix(resolver):
    """'茅台' should match '贵州茅台' via prefix."""
    mentions = [MentionData(name="茅台")]
    result = resolver.resolve(mentions)
    assert result[0].code is not None


def test_resolve_no_match(resolver):
    mentions = [MentionData(name="完全不存在的公司")]
    result = resolver.resolve(mentions)
    assert result[0].code is None
    assert result[0].market == "unknown"


def test_resolve_us_stock(resolver):
    mentions = [MentionData(name="苹果", code="AAPL")]
    result = resolver.resolve(mentions)
    assert result[0].market == "us"


def test_resolve_hk_stock(resolver):
    mentions = [MentionData(name="腾讯", code="00700")]
    result = resolver.resolve(mentions)
    assert result[0].market == "hk"
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest tests/signal/test_asset_resolver.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/signal/asset_resolver.py tests/signal/test_asset_resolver.py
git commit -m "feat(signal): 添加 AssetResolver 标的字典校验层"
```

---

## Task 2: 长字幕 2-pass LLM

**Files:**
- Modify: `src/signal/extractor/video.py`
- Create: `config/prompts/signal_video_summary.yaml`
- Modify: `tests/signal/test_extractor.py`

- [ ] **Step 1: Create summary prompt template**

```yaml
# config/prompts/signal_video_summary.yaml
system_prompt: |
  你是一个财经内容摘要助手。请将以下视频字幕内容压缩为结构化的 markdown 摘要。

  必须保留以下信息（如果原文包含）：
  - 所有提到的标的名称和代码
  - 每个标的的多空观点和论据
  - 关键价位（支撑位、压力位）
  - 操作建议原文

  输出格式：markdown，使用标题分隔不同标的，保留原文关键措辞。
  目标长度：原文的 30%-50%。
  不要添加原文没有的信息。
```

- [ ] **Step 2: Write the failing test — 长字幕触发摘要**

```python
# 追加到 tests/signal/test_extractor.py

from unittest.mock import patch, MagicMock
from src.signal.extractor.video import VideoSignalExtractor, SUMMARY_THRESHOLD


def test_video_extractor_long_transcript_triggers_summary():
    """字幕超过阈值时应先摘要再提取。"""
    extractor = VideoSignalExtractor(litellm_model="test-model")

    long_text = "这是一段关于贵州茅台的分析。" * 2000  # > 6000 chars
    mock_content = MagicMock()
    mock_content.title = "茅台分析"
    mock_transcript = MagicMock()
    mock_transcript.text = long_text
    mock_transcript.quality = "good"
    mock_transcript.source = "platform"
    mock_content.transcripts = [mock_transcript]

    summary_response = MagicMock()
    summary_response.choices = [MagicMock()]
    summary_response.choices[0].message.content = "## 贵州茅台\n看多，目标价2000"

    extract_response = MagicMock()
    extract_response.choices = [MagicMock()]
    extract_response.choices[0].message.content = '{"mentions": [{"name": "贵州茅台", "code": "600519", "sentiment": "bullish", "confidence": 0.8}]}'

    with patch("litellm.completion", side_effect=[summary_response, extract_response]):
        with patch("src.signal.prompt_manager.PromptManager.get_prompt", return_value="test prompt"):
            mentions = extractor.extract(mock_content)

    assert len(mentions) > 0
    assert any("based_on_summary" in m.quality_flags for m in mentions)


def test_video_extractor_short_transcript_no_summary():
    """字幕未超阈值时不摘要。"""
    extractor = VideoSignalExtractor(litellm_model="test-model")

    short_text = "这是一段关于贵州茅台的分析，看多，目标价2000。"
    mock_content = MagicMock()
    mock_content.title = "茅台分析"
    mock_transcript = MagicMock()
    mock_transcript.text = short_text
    mock_transcript.quality = "good"
    mock_transcript.source = "platform"
    mock_content.transcripts = [mock_transcript]

    extract_response = MagicMock()
    extract_response.choices = [MagicMock()]
    extract_response.choices[0].message.content = '{"mentions": [{"name": "贵州茅台", "sentiment": "bullish", "confidence": 0.8}]}'

    with patch("litellm.completion", return_value=extract_response) as mock_llm:
        with patch("src.signal.prompt_manager.PromptManager.get_prompt", return_value="test prompt"):
            mentions = extractor.extract(mock_content)

    assert mock_llm.call_count == 1  # Only extraction, no summary
    assert not any("based_on_summary" in m.quality_flags for m in mentions)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/signal/test_extractor.py::test_video_extractor_long_transcript_triggers_summary -v`
Expected: FAIL (SUMMARY_THRESHOLD not defined / behavior not implemented)

- [ ] **Step 4: Implement 2-pass LLM in VideoSignalExtractor**

修改 `src/signal/extractor/video.py`：

```python
"""Video subtitle signal extractor."""
import json
import logging
import re
from typing import Optional

from src.signal.extractor.base import BaseExtractor, MentionData

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20
SUMMARY_THRESHOLD = 6000


class VideoSignalExtractor(BaseExtractor):
    def __init__(self, litellm_model: str, temperature: float = 0.3, max_tokens: int = 8192, timeout: int = 300):
        self.model = litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def extract(self, content) -> list[MentionData]:
        transcript_text, quality = self._get_best_transcript(content)
        title = content.title or ""

        used_summary = False

        if transcript_text:
            if len(transcript_text) > SUMMARY_THRESHOLD:
                cached_summary = self._get_cached_summary(content)
                if cached_summary:
                    transcript_text = cached_summary
                else:
                    summary = self._summarize_transcript(transcript_text, title)
                    if summary:
                        self._cache_summary(content, summary)
                        transcript_text = summary
                used_summary = len(transcript_text) != len(getattr(content, '_original_transcript', transcript_text) or transcript_text)
                if not cached_summary and summary:
                    used_summary = True
                elif cached_summary:
                    used_summary = True
            full_text = f"标题: {title}\n\n字幕内容:\n{transcript_text}"
        else:
            full_text = title

        if len(full_text.strip()) < MIN_TEXT_LENGTH:
            return []

        title_only = not transcript_text

        from src.signal.prompt_manager import PromptManager

        system_prompt = PromptManager.get_prompt("video")
        if not system_prompt:
            system_prompt = PromptManager.get_prompt("text")
        if not system_prompt:
            return []

        try:
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_text},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

            raw = response.choices[0].message.content
            data = self._parse_json(raw)
            mentions = self._to_mention_data(data)

            for m in mentions:
                if title_only:
                    m.confidence = min(m.confidence, 0.4)
                    if "title_only" not in m.quality_flags:
                        m.quality_flags.append("title_only")
                if quality == "short":
                    if "subtitle_missing" not in m.quality_flags:
                        m.quality_flags.append("subtitle_missing")
                if used_summary:
                    if "based_on_summary" not in m.quality_flags:
                        m.quality_flags.append("based_on_summary")

            return self._apply_quality_rules(mentions, content)

        except Exception as e:
            logger.exception("Video extraction failed: %s", e)
            return []

    def _summarize_transcript(self, transcript: str, title: str) -> Optional[str]:
        from src.signal.prompt_manager import PromptManager
        import litellm

        summary_prompt = PromptManager.get_prompt("video_summary")
        if not summary_prompt:
            logger.warning("No video_summary prompt found, skipping summarization")
            return None

        try:
            user_content = f"标题: {title}\n\n字幕内容:\n{transcript}"
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            summary = response.choices[0].message.content
            if summary and len(summary.strip()) > MIN_TEXT_LENGTH:
                logger.info(
                    "Summarized transcript: %d → %d chars",
                    len(transcript), len(summary),
                )
                return summary.strip()
        except Exception as e:
            logger.exception("Transcript summarization failed: %s", e)

        return None

    def _get_cached_summary(self, content) -> Optional[str]:
        transcripts = getattr(content, "transcripts", None) or []
        for t in transcripts:
            if t.source == "llm_summary" and t.quality == "summarized" and t.text:
                return t.text
        return None

    def _cache_summary(self, content, summary: str) -> None:
        try:
            from src.signal.models import ContentTranscript
            transcript = ContentTranscript(
                content_id=content.id,
                source="llm_summary",
                text=summary,
                quality="summarized",
            )
            session = object.__getattribute__(content, '_sa_instance_state').session
            if session:
                session.add(transcript)
                session.flush()
        except Exception as e:
            logger.warning("Failed to cache summary: %s", e)

    def _get_best_transcript(self, content) -> tuple[Optional[str], Optional[str]]:
        transcripts = getattr(content, "transcripts", None) or []
        if not transcripts:
            return None, None

        priority = {"good": 0, "short": 1, "title_only": 2, "failed": 3, "summarized": 99}
        non_summary = [t for t in transcripts if t.source != "llm_summary"]
        sorted_t = sorted(non_summary, key=lambda t: priority.get(t.quality, 99))

        best = sorted_t[0] if sorted_t else None
        if best and best.quality != "failed":
            return best.text, best.quality
        return None, None

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        return json.loads(raw)

    def _to_mention_data(self, data: dict) -> list[MentionData]:
        mentions_raw = data.get("mentions", [])
        result = []
        for m in mentions_raw:
            if not m.get("name"):
                continue
            result.append(MentionData(
                name=m["name"],
                code=m.get("code") or None,
                asset_type=m.get("asset_type", "stock"),
                market=m.get("market", "unknown"),
                sentiment=m.get("sentiment", "neutral"),
                confidence=float(m.get("confidence", 0.5)),
                is_primary=bool(m.get("is_primary", False)),
                reasoning=m.get("reasoning"),
                trade_advice=m.get("trade_advice") or None,
                key_levels=m.get("key_levels"),
            ))
        return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/signal/test_extractor.py -v -k "video"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/signal/extractor/video.py config/prompts/signal_video_summary.yaml tests/signal/test_extractor.py
git commit -m "feat(signal): 长字幕 2-pass LLM 摘要提取 + based_on_summary 标记"
```

---

## Task 3: 全链路幂等 — 提取前检查

**Files:**
- Modify: `src/signal/extractor/registry.py`
- Modify: `tests/signal/test_pipeline.py`

- [ ] **Step 1: Write the failing test — 已提取内容跳过**

```python
# 追加到 tests/signal/test_pipeline.py

from src.signal.models import Content, SignalMention, ContentCreator
from src.signal.extractor.registry import ExtractorRegistry
from src.signal.extractor.base import MentionData


def test_idempotent_extract_skips_existing_mentions(signal_session):
    """已有 mentions 的 pending_extract 内容应跳过，不重复提取。"""
    creator = ContentCreator(platform="bilibili", platform_uid="123", name="测试UP主")
    signal_session.add(creator)
    signal_session.flush()

    content = Content(
        creator_id=creator.id,
        platform="bilibili",
        platform_content_id="test_idem_001",
        content_type="dynamic",
        display_type="text",
        title="测试内容",
        status="pending_extract",
    )
    signal_session.add(content)
    signal_session.flush()

    existing_mention = SignalMention(
        content_id=content.id,
        creator_id=creator.id,
        asset_name="贵州茅台",
        asset_type="stock",
        sentiment="bullish",
        confidence=0.8,
    )
    signal_session.add(existing_mention)
    signal_session.commit()

    class DummyExtractor:
        def extract(self, c):
            raise AssertionError("Should not be called for already-extracted content")

    registry = ExtractorRegistry(signal_session, {"text": DummyExtractor()})
    result = registry.extract_all()

    assert result.skipped == 1
    assert result.extracted == 0
    assert content.status == "extracted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/signal/test_pipeline.py::test_idempotent_extract_skips_existing_mentions -v`
Expected: FAIL (AssertionError: Should not be called)

- [ ] **Step 3: Add idempotency check to ExtractorRegistry**

修改 `src/signal/extractor/registry.py`，在 `extract_all()` 循环中，提取前检查已有 mentions：

```python
"""Extractor dispatch by display_type."""
import json
import logging

from sqlalchemy.orm import Session

from src.signal.models import Content, SignalMention
from src.signal.extractor.base import BaseExtractor, MentionData, ExtractResult

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    def __init__(self, session: Session, extractors: dict[str, BaseExtractor], asset_resolver=None):
        self.session = session
        self.extractors = extractors
        self.asset_resolver = asset_resolver

    def extract_all(self, contents: list[Content] = None, limit: int = 20) -> ExtractResult:
        result = ExtractResult()

        if contents is None:
            contents = (
                self.session.query(Content)
                .filter(Content.status == "pending_extract")
                .limit(limit)
                .all()
            )

        for content in contents:
            existing_count = (
                self.session.query(SignalMention)
                .filter_by(content_id=content.id)
                .count()
            )
            if existing_count > 0:
                content.status = "extracted"
                result.skipped += 1
                logger.info("Skipped content %d: %d mentions already exist", content.id, existing_count)
                continue

            extractor = self.extractors.get(content.display_type)
            if not extractor:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = f"No extractor for display_type={content.display_type}"
                result.failed += 1
                continue

            try:
                mentions = extractor.extract(content)
                if not mentions:
                    content.status = "extracted"
                    result.extracted += 1
                    continue

                if self.asset_resolver:
                    mentions = self.asset_resolver.resolve(mentions)

                for m_data in mentions:
                    mention = SignalMention(
                        content_id=content.id,
                        creator_id=content.creator_id,
                        asset_name=m_data.name,
                        asset_code=m_data.code,
                        asset_type=m_data.asset_type,
                        market=m_data.market,
                        sentiment=m_data.sentiment,
                        confidence=m_data.confidence,
                        is_primary=m_data.is_primary,
                        reasoning=m_data.reasoning,
                        trade_advice=m_data.trade_advice,
                        key_levels_json=json.dumps(m_data.key_levels or {}, ensure_ascii=False),
                    )
                    mention.set_quality_flags(m_data.quality_flags)
                    self.session.add(mention)

                content.status = "extracted"
                result.extracted += 1

            except Exception as e:
                content.status = "failed"
                content.failure_stage = "extract"
                content.failure_reason = str(e)[:500]
                result.failed += 1
                result.errors.append(f"Content {content.id}: {e}")
                logger.exception("Extraction failed for content %d", content.id)

        self.session.commit()
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/signal/test_pipeline.py::test_idempotent_extract_skips_existing_mentions -v`
Expected: PASS

- [ ] **Step 5: Run all existing signal tests to verify no regression**

Run: `python -m pytest tests/signal/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/signal/extractor/registry.py tests/signal/test_pipeline.py
git commit -m "feat(signal): 全链路幂等 — 提取前检查已有 mentions + AssetResolver 集成口"
```

---

## Task 4: 集成 AssetResolver 到 Pipeline

**Files:**
- Modify: `src/signal/scheduler.py` (AssetResolver 实例化传入)
- Modify: `src/signal/pipeline.py` (传递 asset_resolver 到 registry)

- [ ] **Step 1: Read scheduler.py to understand current extractor registration**

先读取 `src/signal/scheduler.py` 了解当前如何组装 extractors 和 registry。

- [ ] **Step 2: Modify pipeline.py to accept and pass asset_resolver**

在 `SignalPipeline.__init__()` 中接受可选的 `asset_resolver` 参数，传递给 `ExtractorRegistry`。

- [ ] **Step 3: Modify scheduler.py to create AssetResolver instance**

在 `SignalScheduler._execute()` 中，实例化 `AssetResolver()` 并传给 `SignalPipeline`。

- [ ] **Step 4: Run all signal tests**

Run: `python -m pytest tests/signal/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/signal/pipeline.py src/signal/scheduler.py
git commit -m "feat(signal): 集成 AssetResolver 到信号管线"
```

---

## Task 5: API 排序 + 原文数据支持

**Files:**
- Modify: `api/v1/endpoints/signal_overview.py`
- Modify: `api/v1/endpoints/signal_asset.py`
- Modify: `api/v1/schemas/signal.py`

- [ ] **Step 1: Read current API endpoints**

读取 `api/v1/endpoints/signal_overview.py` 和 `api/v1/endpoints/signal_asset.py` 了解现有实现。

- [ ] **Step 2: Add sort_by/sort_order to events endpoint**

在 `GET /api/v1/signals/events` 中增加 `sort_by` 和 `sort_order` 查询参数：

```python
@router.get("/events")
def list_events(
    event_type: str | None = None,
    market: str | None = None,
    asset_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str = "score",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
):
    # ... existing filter logic ...

    sort_column = {
        "score": SignalEvent.score,
        "created_at": SignalEvent.created_at,
        "mention_count": SignalEvent.mention_count,
    }.get(sort_by, SignalEvent.score)

    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # ... existing pagination ...
```

- [ ] **Step 3: Add MentionResponse extended fields to schema**

在 `api/v1/schemas/signal.py` 中扩展 `MentionResponse`：

```python
class MentionResponse(BaseModel):
    # ... existing fields ...
    content_text: str | None = None
    transcript_text: str | None = None
    summary_text: str | None = None
```

- [ ] **Step 4: Add include_content param to asset mentions endpoint**

在 `GET /api/v1/signals/assets/{identifier}/mentions` 中增加 `include_content` 参数，为 true 时填充 `content_text` / `transcript_text` / `summary_text`。

- [ ] **Step 5: Run py_compile to verify syntax**

Run: `python -m py_compile api/v1/endpoints/signal_overview.py && python -m py_compile api/v1/endpoints/signal_asset.py && python -m py_compile api/v1/schemas/signal.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add api/v1/endpoints/signal_overview.py api/v1/endpoints/signal_asset.py api/v1/schemas/signal.py
git commit -m "feat(signal): API 排序参数 + mention 原文数据字段"
```

---

## Task 6: 前端类型 + API Client 更新

**Files:**
- Modify: `apps/dsa-web/src/types/signal.ts`
- Modify: `apps/dsa-web/src/api/signal.ts`

- [ ] **Step 1: 扩展类型定义**

在 `apps/dsa-web/src/types/signal.ts` 中扩展：

```typescript
// 追加到 Mention interface
export interface Mention {
  // ... existing fields ...
  contentText?: string;
  transcriptText?: string;
  summaryText?: string;
}

// 新增事件列表查询参数类型
export interface EventListParams {
  eventType?: string;
  market?: string;
  assetType?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: 'score' | 'created_at' | 'mention_count';
  sortOrder?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

// 新增 mention 查询参数
export interface MentionListParams {
  sentiment?: string;
  creatorId?: number;
  includeContent?: boolean;
  limit?: number;
  offset?: number;
}
```

- [ ] **Step 2: 更新 API client**

在 `apps/dsa-web/src/api/signal.ts` 中：

- 更新 `listEvents` 方法接受 `EventListParams`，传递 `sort_by`/`sort_order`
- 更新 `getAssetMentions` 方法接受 `MentionListParams`，传递 `include_content`
- 更新 snake_case → camelCase 映射，增加 `content_text`/`transcript_text`/`summary_text`

- [ ] **Step 3: Run lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add apps/dsa-web/src/types/signal.ts apps/dsa-web/src/api/signal.ts
git commit -m "feat(signal): 前端类型 + API client 排序和原文数据支持"
```

---

## Task 7: 前端 — EventCard + StatusBar 组件

**Files:**
- Create: `apps/dsa-web/src/components/signal/EventCard.tsx`
- Create: `apps/dsa-web/src/components/signal/StatusBar.tsx`

- [ ] **Step 1: 创建 EventCard 组件**

事件卡片组件，展示：事件类型标签、标的名称、得分、UP 主数、提及数、最高权重 UP 主。点击触发回调。

```tsx
// apps/dsa-web/src/components/signal/EventCard.tsx
import { type SignalEvent } from '../../types/signal';

const EVENT_TYPE_CONFIG = {
  opportunity: { label: '机会', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200', icon: '🟢' },
  risk: { label: '风险', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200', icon: '🔴' },
  conflict: { label: '分歧', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200', icon: '🟡' },
  watch: { label: '观察', color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200', icon: '⚪' },
} as const;

interface EventCardProps {
  event: SignalEvent;
  onClick: (event: SignalEvent) => void;
  isSelected?: boolean;
  showTypeLabel?: boolean;
}

export default function EventCard({ event, onClick, isSelected, showTypeLabel = false }: EventCardProps) {
  const config = EVENT_TYPE_CONFIG[event.eventType as keyof typeof EVENT_TYPE_CONFIG] || EVENT_TYPE_CONFIG.watch;

  return (
    <div
      className={`rounded-lg border p-4 cursor-pointer transition-all hover:shadow-md ${
        isSelected ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800' : 'border-gray-200 dark:border-gray-700'
      }`}
      onClick={() => onClick(event)}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {showTypeLabel && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
              {config.icon} {config.label}
            </span>
          )}
          <span className="font-semibold text-base">{event.assetName}</span>
          {event.assetCode && (
            <span className="text-xs text-gray-500">{event.assetCode}</span>
          )}
        </div>
        <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
          {event.score?.toFixed(1)}
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
        <span>{event.creatorCount}位UP主</span>
        <span>{event.mentionCount}条提及</span>
        {event.topCreatorName && <span>最高权重：{event.topCreatorName}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 StatusBar 组件**

```tsx
// apps/dsa-web/src/components/signal/StatusBar.tsx
import { useEffect, useState } from 'react';
import { signalApi } from '../../api/signal';

export default function StatusBar() {
  const [stats, setStats] = useState<{
    creatorsCovered: number;
    creatorsTotal: number;
    contentCount: number;
    lastUpdated: string | null;
  } | null>(null);

  useEffect(() => {
    signalApi.getOverviewStats().then(setStats).catch(() => {});
  }, []);

  if (!stats) return null;

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg text-sm text-gray-600 dark:text-gray-400">
      <span>
        今日覆盖 <strong>{stats.creatorsCovered}/{stats.creatorsTotal}</strong> 位创作者
      </span>
      <span>·</span>
      <span><strong>{stats.contentCount}</strong> 条信号</span>
      {stats.lastUpdated && (
        <>
          <span>·</span>
          <span>最近更新 {stats.lastUpdated}</span>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add apps/dsa-web/src/components/signal/EventCard.tsx apps/dsa-web/src/components/signal/StatusBar.tsx
git commit -m "feat(signal): 添加 EventCard 和 StatusBar 前端组件"
```

---

## Task 8: 前端 — CreatorTimeline + ContentViewer 组件

**Files:**
- Create: `apps/dsa-web/src/components/signal/CreatorTimeline.tsx`
- Create: `apps/dsa-web/src/components/signal/ContentViewer.tsx`

- [ ] **Step 1: 创建 CreatorTimeline 组件**

UP 主动态时间线：以 UP 主维度聚合 mentions，展示观点变化轨迹。

```tsx
// apps/dsa-web/src/components/signal/CreatorTimeline.tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { type Mention } from '../../types/signal';

interface CreatorTimelineProps {
  mentions: Mention[];
}

interface CreatorGroup {
  creatorName: string;
  creatorWeight: number;
  items: Mention[];
}

const SENTIMENT_CONFIG = {
  bullish: { label: '看多', color: 'text-green-600 dark:text-green-400' },
  bearish: { label: '看空', color: 'text-red-600 dark:text-red-400' },
  neutral: { label: '中性', color: 'text-gray-600 dark:text-gray-400' },
} as const;

export default function CreatorTimeline({ mentions }: CreatorTimelineProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const groups: CreatorGroup[] = Object.values(
    mentions.reduce<Record<string, CreatorGroup>>((acc, m) => {
      const key = m.creatorName || 'unknown';
      if (!acc[key]) {
        acc[key] = { creatorName: key, creatorWeight: m.creatorWeight || 1.0, items: [] };
      }
      acc[key].items.push(m);
      return acc;
    }, {})
  ).sort((a, b) => b.creatorWeight - a.creatorWeight);

  const toggle = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">UP主动态时间线</h4>
      {groups.map((g) => (
        <div key={g.creatorName} className="border rounded-lg dark:border-gray-700">
          <button
            className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
            onClick={() => toggle(g.creatorName)}
          >
            <div className="flex items-center gap-2">
              {expanded.has(g.creatorName) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="font-medium">{g.creatorName}</span>
              {g.creatorWeight !== 1.0 && (
                <span className="text-xs text-blue-500">权重 {g.creatorWeight}</span>
              )}
            </div>
            <span className="text-xs text-gray-400">{g.items.length}条</span>
          </button>
          {expanded.has(g.creatorName) && (
            <div className="px-3 pb-2 space-y-1 border-t dark:border-gray-700">
              {g.items
                .sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime())
                .map((m) => {
                  const sc = SENTIMENT_CONFIG[m.sentiment as keyof typeof SENTIMENT_CONFIG] || SENTIMENT_CONFIG.neutral;
                  return (
                    <div key={m.id} className="flex items-center gap-3 py-1 text-xs">
                      <span className="text-gray-400 w-24 shrink-0">
                        {m.createdAt ? new Date(m.createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                      </span>
                      <span className={`font-medium ${sc.color}`}>{sc.label}</span>
                      <span className="text-gray-400">{(m.confidence * 100).toFixed(0)}%</span>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 创建 ContentViewer 组件**

原文/摘要内联查看组件。可展开式区域。

```tsx
// apps/dsa-web/src/components/signal/ContentViewer.tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { type Mention } from '../../types/signal';

interface ContentViewerProps {
  mention: Mention;
}

export default function ContentViewer({ mention }: ContentViewerProps) {
  const [showContent, setShowContent] = useState(false);
  const [showSummary, setShowSummary] = useState(false);

  const hasSummary = mention.qualityFlags?.includes('based_on_summary') && mention.summaryText;
  const hasContent = mention.contentText || mention.transcriptText;

  if (!hasContent && !hasSummary) return null;

  return (
    <div className="space-y-1 text-sm">
      {hasContent && (
        <div>
          <button
            className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline text-xs"
            onClick={() => setShowContent(!showContent)}
          >
            {showContent ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            原文内容
          </button>
          {showContent && (
            <div className="mt-1 p-2 bg-gray-50 dark:bg-gray-800 rounded text-xs text-gray-700 dark:text-gray-300 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {mention.transcriptText || mention.contentText}
            </div>
          )}
        </div>
      )}
      {hasSummary && (
        <div>
          <button
            className="flex items-center gap-1 text-purple-600 dark:text-purple-400 hover:underline text-xs"
            onClick={() => setShowSummary(!showSummary)}
          >
            {showSummary ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            摘要 <span className="text-gray-400">(基于摘要提取)</span>
          </button>
          {showSummary && (
            <div className="mt-1 p-2 bg-purple-50 dark:bg-purple-900/20 rounded text-xs text-gray-700 dark:text-gray-300 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {mention.summaryText}
            </div>
          )}
        </div>
      )}
      {mention.sourceUrl && (
        <a
          href={mention.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-blue-500"
        >
          <ExternalLink size={10} /> 查看原文
        </a>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add apps/dsa-web/src/components/signal/CreatorTimeline.tsx apps/dsa-web/src/components/signal/ContentViewer.tsx
git commit -m "feat(signal): 添加 CreatorTimeline 和 ContentViewer 前端组件"
```

---

## Task 9: 前端 — ResearchSidebar 组件

**Files:**
- Create: `apps/dsa-web/src/components/signal/ResearchSidebar.tsx`

- [ ] **Step 1: 创建 ResearchSidebar 组件**

研究态侧边栏：标的信息、多空比例条、UP 主时间线、mention 详情卡片。

```tsx
// apps/dsa-web/src/components/signal/ResearchSidebar.tsx
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { signalApi } from '../../api/signal';
import { type SignalEvent, type Mention } from '../../types/signal';
import CreatorTimeline from './CreatorTimeline';
import ContentViewer from './ContentViewer';

interface ResearchSidebarProps {
  event: SignalEvent | null;
  onClose: () => void;
}

const SENTIMENT_COLORS = {
  bullish: 'bg-green-500',
  bearish: 'bg-red-500',
  neutral: 'bg-gray-400',
};

export default function ResearchSidebar({ event, onClose }: ResearchSidebarProps) {
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!event) {
      setMentions([]);
      return;
    }
    setLoading(true);
    const identifier = event.assetCode || encodeURIComponent(event.assetName);
    signalApi
      .getAssetMentions(identifier, { includeContent: true })
      .then(setMentions)
      .catch(() => setMentions([]))
      .finally(() => setLoading(false));
  }, [event]);

  if (!event) return null;

  const total = event.bullishCount + event.bearishCount + event.neutralCount || 1;
  const bullPct = (event.bullishCount / total) * 100;
  const bearPct = (event.bearishCount / total) * 100;
  const neutPct = (event.neutralCount / total) * 100;

  return (
    <div className="fixed right-0 top-0 h-full w-[420px] bg-white dark:bg-gray-900 border-l dark:border-gray-700 shadow-xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b dark:border-gray-700">
        <div>
          <h3 className="text-lg font-semibold">{event.assetName}</h3>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            {event.assetCode && <span>{event.assetCode}</span>}
            <span>{event.assetType}</span>
            <span>{event.market}</span>
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
          <X size={18} />
        </button>
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Sentiment bar */}
        <div>
          <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">多空分布</h4>
          <div className="flex h-3 rounded-full overflow-hidden">
            {bullPct > 0 && <div className={`${SENTIMENT_COLORS.bullish}`} style={{ width: `${bullPct}%` }} />}
            {neutPct > 0 && <div className={`${SENTIMENT_COLORS.neutral}`} style={{ width: `${neutPct}%` }} />}
            {bearPct > 0 && <div className={`${SENTIMENT_COLORS.bearish}`} style={{ width: `${bearPct}%` }} />}
          </div>
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>看多 {event.bullishCount}</span>
            <span>中性 {event.neutralCount}</span>
            <span>看空 {event.bearishCount}</span>
          </div>
        </div>

        {/* Creator Timeline */}
        {mentions.length > 0 && <CreatorTimeline mentions={mentions} />}

        {/* Mention details */}
        {loading ? (
          <div className="text-center text-gray-400 py-4">加载中...</div>
        ) : (
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              信号详情 ({mentions.length}条)
            </h4>
            {mentions.map((m) => (
              <div key={m.id} className="border rounded-lg p-3 dark:border-gray-700 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium">{m.creatorName}</span>
                    {m.creatorWeight !== 1.0 && (
                      <span className="text-xs text-blue-500">×{m.creatorWeight}</span>
                    )}
                  </div>
                  <span className={`text-xs font-medium ${
                    m.sentiment === 'bullish' ? 'text-green-600' :
                    m.sentiment === 'bearish' ? 'text-red-600' : 'text-gray-500'
                  }`}>
                    {m.sentiment === 'bullish' ? '看多' : m.sentiment === 'bearish' ? '看空' : '中性'}
                    {' '}{(m.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {m.contentTitle && (
                  <div className="text-xs text-gray-500 truncate">{m.contentTitle}</div>
                )}
                {m.reasoning && (
                  <div className="text-xs text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded p-2">
                    {m.reasoning}
                  </div>
                )}
                {m.tradeAdvice && (
                  <div className="text-xs text-blue-700 dark:text-blue-300">
                    💡 {m.tradeAdvice}
                  </div>
                )}
                {m.qualityFlags && m.qualityFlags.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {m.qualityFlags.map((f) => (
                      <span key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300">
                        {f}
                      </span>
                    ))}
                  </div>
                )}
                <ContentViewer mention={m} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add apps/dsa-web/src/components/signal/ResearchSidebar.tsx
git commit -m "feat(signal): 添加 ResearchSidebar 研究态侧边栏组件"
```

---

## Task 10: 前端 — SignalBriefingPage + SignalSettingsPage

**Files:**
- Create: `apps/dsa-web/src/pages/signal/SignalBriefingPage.tsx`
- Create: `apps/dsa-web/src/pages/signal/SignalSettingsPage.tsx`
- Modify: `apps/dsa-web/src/pages/signal/index.ts`

- [ ] **Step 1: 创建 SignalBriefingPage**

简报流主视图：StatusBar + Tab（全部/机会/风险/分歧/观察）+ EventCard 列表 + ResearchSidebar。

```tsx
// apps/dsa-web/src/pages/signal/SignalBriefingPage.tsx
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { signalApi } from '../../api/signal';
import { type SignalEvent } from '../../types/signal';
import StatusBar from '../../components/signal/StatusBar';
import EventCard from '../../components/signal/EventCard';
import ResearchSidebar from '../../components/signal/ResearchSidebar';

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'opportunity', label: '机会' },
  { key: 'risk', label: '风险' },
  { key: 'conflict', label: '分歧' },
  { key: 'watch', label: '观察' },
] as const;

export default function SignalBriefingPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>('all');
  const [events, setEvents] = useState<SignalEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<SignalEvent | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        sortBy: 'score',
        sortOrder: 'desc',
        limit: 100,
      };
      if (activeTab !== 'all') {
        params.eventType = activeTab;
      }
      const data = await signalApi.listEvents(params);
      setEvents(data);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  return (
    <div className="h-full flex flex-col">
      {/* Status bar */}
      <div className="px-4 pt-4">
        <StatusBar />
      </div>

      {/* Tabs + Settings */}
      <div className="flex items-center justify-between px-4 py-3 border-b dark:border-gray-700">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                  : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => navigate('/signals/settings')}
          className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
          title="设置"
        >
          <Settings2 size={18} />
        </button>
      </div>

      {/* Event list */}
      <div className={`flex-1 overflow-y-auto p-4 ${selectedEvent ? 'pr-[440px]' : ''}`}>
        {loading ? (
          <div className="text-center text-gray-400 py-8">加载中...</div>
        ) : events.length === 0 ? (
          <div className="text-center text-gray-400 py-8">暂无信号事件</div>
        ) : (
          <div className="space-y-3">
            {events.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                onClick={setSelectedEvent}
                isSelected={selectedEvent?.id === event.id}
                showTypeLabel={activeTab === 'all'}
              />
            ))}
          </div>
        )}
      </div>

      {/* Research sidebar */}
      <ResearchSidebar event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}
```

- [ ] **Step 2: 创建 SignalSettingsPage**

设置区：三个 Tab（UP 主管理、采集质量、内容队列），复用现有组件。

```tsx
// apps/dsa-web/src/pages/signal/SignalSettingsPage.tsx
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import CreatorManagePage from './CreatorManagePage';
import QualityDashboard from './QualityDashboard';
import ContentQueuePage from './ContentQueuePage';

const SETTINGS_TABS = [
  { key: 'creators', label: 'UP主管理' },
  { key: 'quality', label: '采集质量' },
  { key: 'content', label: '内容队列' },
] as const;

export default function SignalSettingsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'creators';

  const setActiveTab = (tab: string) => {
    setSearchParams({ tab });
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b dark:border-gray-700">
        <button
          onClick={() => navigate('/signals')}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
        >
          <ArrowLeft size={18} />
        </button>
        <h2 className="text-lg font-semibold">信号设置</h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-4 py-2 border-b dark:border-gray-700">
        {SETTINGS_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'creators' && <CreatorManagePage />}
        {activeTab === 'quality' && <QualityDashboard />}
        {activeTab === 'content' && <ContentQueuePage />}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 更新 index.ts 导出**

```typescript
// apps/dsa-web/src/pages/signal/index.ts
export { default as SignalBriefingPage } from './SignalBriefingPage';
export { default as SignalSettingsPage } from './SignalSettingsPage';
export { default as QualityDashboard } from './QualityDashboard';
export { default as ContentQueuePage } from './ContentQueuePage';
export { default as AssetDetailPage } from './AssetDetailPage';
export { default as CreatorManagePage } from './CreatorManagePage';
// SignalOverviewPage is replaced by SignalBriefingPage
```

- [ ] **Step 4: Run lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/pages/signal/SignalBriefingPage.tsx apps/dsa-web/src/pages/signal/SignalSettingsPage.tsx apps/dsa-web/src/pages/signal/index.ts
git commit -m "feat(signal): 添加简报流主视图 + 设置区页面"
```

---

## Task 11: 路由 + 导航更新

**Files:**
- Modify: `apps/dsa-web/src/App.tsx`
- Modify: `apps/dsa-web/src/components/layout/SidebarNav.tsx`

- [ ] **Step 1: 更新路由**

在 `apps/dsa-web/src/App.tsx` 中：

- 将 `import { SignalOverviewPage, ... }` 替换为 `import { SignalBriefingPage, SignalSettingsPage }`
- 替换路由：

```tsx
// 旧路由 → 新路由
<Route path="/signals" element={<SignalBriefingPage />} />
<Route path="/signals/settings" element={<SignalSettingsPage />} />
// 保留 asset 路由作为向后兼容的重定向（可选）
```

- [ ] **Step 2: SidebarNav 不需要修改**

`SidebarNav.tsx` 中信号入口已经是 `/signals`，不需要变更。

- [ ] **Step 3: Run build**

Run: `cd apps/dsa-web && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add apps/dsa-web/src/App.tsx
git commit -m "feat(signal): 路由重构 — 5 页面 → 简报流 + 设置区"
```

---

## Task 12: 文档更新

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 CHANGELOG**

在 `[Unreleased]` 段追加条目：

```markdown
- [改进] 信号系统迭代：长字幕 2-pass LLM 摘要提取（超 6000 汉字先摘要再提取 + `based_on_summary` 质量标记）
- [新功能] 信号系统标的字典校验层（AssetResolver，复用 stocks.index.json 自动匹配 asset_code/market）
- [改进] 信号系统全链路幂等（提取前检查已有 mentions，避免重复提取）
- [改进] 信号事件 API 支持 sort_by/sort_order 排序参数，mention API 支持 include_content 返回原文数据
- [改进] 信号系统前端重构：5 页面 → 简报流（Tab 分类 + 加权得分排序）+ 研究态侧边栏 + 设置区
- [新功能] 信号研究态侧边栏：UP 主动态时间线、原文/摘要内联查看、多空比例条
- [新功能] 信号简报流状态条：展示创作者覆盖率和信号数量
```

- [ ] **Step 2: Commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: 更新 CHANGELOG 信号系统 V1 迭代条目"
```

---

## 自检

### Spec 覆盖

| Spec 需求 | 对应 Task |
| --- | --- |
| §2.1 长字幕 2-pass LLM | Task 2 |
| §2.2 AssetResolver | Task 1 + Task 4 |
| §2.3 全链路幂等 | Task 3 |
| §2.4 API 排序支持 | Task 5 |
| §3.1 路由重构 | Task 11 |
| §3.2 简报流主视图 | Task 7 + Task 10 |
| §3.3 研究态侧边栏 | Task 8 + Task 9 |
| §3.4 设置区 | Task 10 |
| §3.5 组件复用 | Task 10 (SignalSettingsPage 复用现有组件) |
| 文档更新 | Task 12 |

### Placeholder 扫描

无 TBD / TODO / 不完整引用。

### 类型一致性

- `MentionData`：Task 1 和 Task 2 使用相同的 `src/signal/extractor/base.py` 定义
- `SignalEvent` / `Mention`：前端类型在 Task 6 中统一扩展
- `signalApi.listEvents`：Task 6 扩展参数，Task 10 使用
- `signalApi.getAssetMentions`：Task 6 扩展参数，Task 9 使用
