# 统一信号系统 V1 — 设计文档

> **日期**: 2026-05-12
> **状态**: 已批准
> **范围**: Bilibili 信号提取链路 V1 —— 采集→标准化→补全→提取→单标的事件→5 个前端页面
> **预估周期**: 4-6 周
> **前置文档**:
>   - `docs/temp/2026-05-10-unified-signal-system-technical-prd.md` (产品 PRD)
>   - `docs/temp/2026-05-11-unified-signal-system-technical-decisions.md` (技术决策交接)

---

## 1. 设计目标

把分散在 Bilibili UP 主内容里的股票、ETF、指数、板块观点，转换成可追溯的结构化信号，并在前端提供采集质量、处理队列、信号看板、单标的详情和 UP 主管理。

V1 只做 Bilibili 平台、单标的事件、人工 UP 主权重。不做决策融合、实时推送、自动准确率、综合日报、回测闭环。

### 1.1 V1 需要回答的问题

- 今天系统采集了多少内容？
- 哪些 UP 主覆盖到了，哪些没有？
- 哪些内容成功提取了信号？哪些失败了，原因是什么？
- 哪些标的被提到？每个标的的观点来自哪些 UP 主、哪些内容、哪些原文证据？
- 同一标的是否形成机会、风险、分歧或观察信号？
- 用户配置的高权重 UP 主是否影响信号排序？

### 1.2 V1 重点指标

| 指标 | 说明 |
| --- | --- |
| 内容数 | 指定时间范围内采集到的内容总量 |
| 内容提取成功率 | 成功完成信号提取的内容占比 |
| UP 主覆盖率 | 已启用 UP 主中，本轮成功采集到内容或确认无新增内容的占比 |
| 失败可解释率 | 失败内容中，有明确失败阶段和可读失败原因的占比 |

---

## 2. 架构决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 代码组织 | `src/signal/` 独立子包 | 清晰边界，不污染现有代码，V4 融合时自然 import |
| 进程集成 | 同进程，共用 FastAPI / SQLite / APScheduler | 部署简单，共享基础设施 |
| 分支策略 | 新分支从 main 拉出，参考现有信号分支但重写 | 避免继承分散的实现 |
| 信号事实层 | `signal_mentions` 是唯一事实源，不写 TradeSignal 镜像 | 减少双写和一致性问题 |
| 内容形态 | 产品层 3 类（text / image_text / video_subtitle），内部保留细粒度类型 | PRD 要求，简化前端和提取器 |
| UP 主权重 | V1 仅人工配置，不自动调整 | PRD V1 范围 |
| 事件类型 | opportunity / risk / conflict / watch | 与现有事件枚举一致 |

---

## 3. 主链路

```
collect → enrich → extract → build_events → compute_stats
```

每一步输出：开始时间、结束时间、成功数、失败数、跳过数、失败原因列表。

### 3.1 数据流

```
1. [定时/手动] BilibiliCollector.fetch_feed()
   → bili feed --yaml → 解析 → 标准化 → 写入 contents + content_media
   → 新内容 status = collected → pending_enrich (需补全) 或 pending_extract (纯文本)

2. [紧接] ContentEnricher.enrich()
   → 查 status=pending_enrich 的 contents
   → 视频：平台字幕 → Whisper 兜底 → 写 content_transcripts
   → 图文：Vision LLM OCR → 更新 content_media.ocr_text
   → 更新 status = pending_extract 或 failed

3. [紧接] ExtractorRegistry.extract_all()
   → 查 status=pending_extract 的 contents
   → 按 display_type 分发到对应提取器
   → LLM 提取 → 写 signal_mentions + 更新 status = extracted
   → 失败 → status = failed + 记录 failure_stage/reason

4. [紧接] SignalEventBuilder.build(date)
   → 读取当日所有 signal_mentions
   → 按 (asset_code 或 asset_name) 分组
   → 评分 + 分类 → 写 signal_events

5. [紧接] QualityTracker.compute(run_result)
   → 汇总各步骤统计 → 供 API 查询
```

---

## 4. 数据模型

所有模型定义在 `src/signal/models.py`，使用与 `src/storage.py` 相同的 SQLAlchemy declarative base 和 DB 连接。

### 4.1 content_creators

UP 主配置。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | 自增主键 |
| platform | str NOT NULL | bilibili（V1 固定） |
| platform_uid | str NOT NULL | B 站 UID |
| name | str NOT NULL | UP 主名称 |
| category | str | 分类标签 |
| is_active | bool DEFAULT true | 是否启用 |
| manual_weight | float DEFAULT 1.0 | 人工权重 (0.1-2.0) |
| fetch_interval_min | int DEFAULT 60 | 抓取间隔（分钟） |
| notes | str | 备注 |
| last_fetch_at | datetime | 最近采集时间 |
| created_at | datetime | |
| updated_at | datetime | |

约束：UNIQUE(platform, platform_uid)

### 4.2 contents

平台无关内容记录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| creator_id | int FK(content_creators.id) | |
| platform | str NOT NULL | bilibili |
| platform_content_id | str NOT NULL | B 站动态 ID / BV 号 |
| content_type | str NOT NULL | video / article / dynamic / image / forward |
| display_type | str NOT NULL | text / image_text / video_subtitle |
| title | str | |
| text | text | 正文 |
| url | str | 原文链接 |
| raw_json | JSON | 原始载荷 |
| status | str NOT NULL DEFAULT 'collected' | collected / pending_enrich / pending_extract / extracted / low_confidence / failed / ignored |
| failure_stage | str | collect / normalize / enrich / extract / resolve |
| failure_reason | str | 可读失败原因 |
| suggested_action | str | retry / wait / ignore / review |
| published_at | datetime | |
| created_at | datetime | |
| updated_at | datetime | |

约束：UNIQUE(platform, platform_content_id)

### 4.3 content_media

内容附属媒体。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| content_id | int FK(contents.id) | |
| media_type | str NOT NULL | image / video / audio |
| url | str | |
| ocr_text | text | 图片 OCR 文字 |
| created_at | datetime | |

### 4.4 content_transcripts

字幕和转录。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| content_id | int FK(contents.id) | |
| source | str NOT NULL | platform / whisper / manual |
| text | text | 纯文本字幕 |
| quality | str NOT NULL | good / short / title_only / failed |
| created_at | datetime | |

### 4.5 signal_mentions

原子事实层：某 UP 主在某内容中提到某标的。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| content_id | int FK(contents.id) | |
| creator_id | int FK(content_creators.id) | |
| asset_name | str NOT NULL | 标的名称 |
| asset_code | str | 标的代码，未识别时为空 |
| asset_type | str NOT NULL | stock / etf / index / sector |
| market | str NOT NULL DEFAULT 'unknown' | a_share / hk / us / unknown |
| sentiment | str NOT NULL | bullish / bearish / neutral |
| confidence | float NOT NULL | 0.0-1.0 |
| is_primary | bool DEFAULT false | 是否主标的 |
| reasoning | text | 原文证据 |
| trade_advice | text | 操作建议原文，无则空，不编造 |
| key_levels_json | JSON | 关键价位 {"support": [], "resistance": []} |
| quality_flags | JSON DEFAULT '[]' | 质量标记列表 |
| created_at | datetime | |

质量标记枚举值：
- `subtitle_missing` — 视频无字幕
- `title_only` — 仅基于标题提取
- `image_ocr_incomplete` — 图片 OCR 不完整
- `code_unresolved` — 标的代码未识别
- `name_ambiguous` — 标的名称存在歧义
- `low_llm_confidence` — LLM 置信度低 (< 0.4)
- `no_trade_advice` — 原文无明确操作建议

### 4.6 signal_events

单标的事件，面向用户的聚合层。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| asset_name | str NOT NULL | |
| asset_code | str | |
| asset_type | str NOT NULL | |
| market | str NOT NULL | |
| event_type | str NOT NULL | opportunity / risk / conflict / watch |
| event_date | date NOT NULL | |
| score | float | 事件强度 0-100 |
| bullish_count | int DEFAULT 0 | |
| bearish_count | int DEFAULT 0 | |
| neutral_count | int DEFAULT 0 | |
| creator_count | int DEFAULT 0 | 涉及 UP 主数 |
| mention_count | int DEFAULT 0 | |
| top_creator_name | str | 最高权重 UP 主 |
| evidence_json | JSON | 完整证据链 |
| created_at | datetime | |
| updated_at | datetime | |

约束：UNIQUE(asset_name, asset_type, event_date)（包含 asset_type 防止同名不同类型冲突；优先用 asset_name 而非 asset_code，因为代码可能未识别）

### 4.7 evidence_json 结构

```json
[
  {
    "mention_id": 123,
    "content_id": 456,
    "creator_id": 789,
    "creator_name": "财经老王",
    "creator_weight": 1.5,
    "content_title": "今天聊聊茅台",
    "content_type": "video",
    "display_type": "video_subtitle",
    "sentiment": "bullish",
    "confidence": 0.85,
    "reasoning": "茅台1800以下都是买点...",
    "trade_advice": "可以分批建仓",
    "source_url": "https://www.bilibili.com/video/BV...",
    "published_at": "2026-05-12T10:30:00"
  }
]
```

---

## 5. 模块职责

### 5.1 目录结构

```
src/signal/
  __init__.py
  models.py              # 6 张表
  pipeline.py            # SignalPipeline — 主链路编排
  collector.py           # BilibiliCollector — bili CLI 采集
  enricher.py            # ContentEnricher — 字幕/OCR 补全
  extractor/
    __init__.py
    base.py              # BaseExtractor 接口
    text.py              # TextSignalExtractor
    image.py             # ImageSignalExtractor
    video.py             # VideoSignalExtractor
    registry.py          # ExtractorRegistry — 按 display_type 分发
  event_builder.py       # SignalEventBuilder — mentions → events
  quality.py             # QualityTracker — 采集/提取统计
  scheduler.py           # SignalScheduler — APScheduler 集成
  prompt_manager.py      # PromptManager — 加载 YAML prompt

config/prompts/
  signal_text.yaml       # 纯文本 prompt
  signal_image.yaml      # 图文 prompt（含 Vision 指令）
  signal_video.yaml      # 视频字幕 prompt
```

### 5.2 各模块接口

#### BilibiliCollector

```python
class BilibiliCollector:
    def fetch_feed(self) -> CollectResult:
        """调用 bili feed --yaml，解析并写入 contents + content_media。
        返回 CollectResult(new=N, duplicate=N, skipped=N, failed=N, errors=[...])
        """

    def _parse_item(self, item: dict) -> Content:
        """单条动态解析 + content_type → display_type 映射"""

    def _match_creator(self, uid: str, name: str) -> ContentCreator | None:
        """匹配 UP 主：UID 优先，名称 fallback"""
```

#### ContentEnricher

```python
class ContentEnricher:
    def enrich_batch(self, contents: list[Content]) -> EnrichResult:
        """批量补全。视频走字幕链路，图文走 OCR 链路。
        返回 EnrichResult(enriched=N, failed=N, skipped=N, errors=[...])
        """

    def _enrich_video(self, content: Content) -> None:
        """平台字幕 → Whisper 兜底 → 写 content_transcripts"""

    def _enrich_image(self, content: Content) -> None:
        """Vision LLM OCR → 更新 content_media.ocr_text"""
```

字幕策略（与现有分支验证的方向一致）：
1. `bili video <bvid> --subtitle --yaml` 获取平台字幕
2. 失败则 `bili audio <bvid>` + `whisper --model turbo --language zh`
3. 字幕 < 50 字符标记 quality=short
4. 完全失败标记 quality=failed，content status 降级但不阻塞
5. Whisper 超时保护：300 秒
6. 同一时间最多 1 个转录任务

#### ExtractorRegistry + Extractors

```python
class ExtractorRegistry:
    def extract_all(self, contents: list[Content]) -> ExtractResult:
        """按 display_type 分发到对应提取器"""

class BaseExtractor:
    def extract(self, content: Content) -> list[MentionData]:
        """提取信号，返回结构化 mention 列表"""

class TextSignalExtractor(BaseExtractor): ...   # display_type = text
class ImageSignalExtractor(BaseExtractor): ...   # display_type = image_text
class VideoSignalExtractor(BaseExtractor): ...   # display_type = video_subtitle
```

LLM 调用规则：
- 使用 LiteLLM，复用现有 `cfg.litellm_model` 配置
- 图文使用 Vision LLM（复用现有 vision model 优先级逻辑）
- temperature: 0.2-0.3
- max_tokens: 8192
- 输出格式: JSON
- 文本 < 20 字符跳过
- JSON 解析支持 markdown code block 包裹

Prompt 输出契约（三类 prompt 共享）：

```json
{
  "mentions": [
    {
      "name": "贵州茅台",
      "code": "600519",
      "asset_type": "stock",
      "market": "a_share",
      "sentiment": "bullish",
      "confidence": 0.85,
      "is_primary": true,
      "reasoning": "UP 主原话证据...",
      "trade_advice": "操作建议原文，无则空字符串",
      "key_levels": {"support": [1750], "resistance": [1850]}
    }
  ]
}
```

质量规则（提取后处理）：
- 仅标题提取 → confidence 上限 0.4 + `title_only` flag
- 无原文 trade_advice 时字段置空 + `no_trade_advice` flag
- code 为空 → `code_unresolved` flag
- LLM confidence < 0.4 → `low_llm_confidence` flag
- 带 `code_unresolved` 的 mention 不触发 opportunity 事件

#### SignalEventBuilder

```python
class SignalEventBuilder:
    def build(self, date: date) -> list[SignalEvent]:
        """读取当日所有 mentions，按标的分组，评分+分类，写入 signal_events。"""
```

事件类型判定规则：
- **opportunity**: bullish 占比 >= 60% 且 creator_count >= 2，或单个高权重 UP 主 (weight >= 1.5) 明确看多
- **risk**: bearish 占比 >= 60% 且 creator_count >= 2，或单个高权重 UP 主明确看空
- **conflict**: bullish_count >= 2 且 bearish_count >= 2
- **watch**: 不满足以上条件的所有标的事件

评分因子（均归一化到 0-100）：
- sentiment 倾向强度：30%
- confidence 加权均值：20%
- creator_count 和 creator 权重：30%
- 有 trade_advice 的 mention 比例：10%
- is_primary 的 mention 比例：10%

#### SignalPipeline

```python
class SignalPipeline:
    def run(self, max_contents: int = 50, process_limit: int = 20) -> PipelineResult:
        """串联主链路五步，返回完整运行结果。"""
```

PipelineResult 包含各步骤的 result 对象 + 总耗时 + 是否成功。

#### SignalScheduler

```python
class SignalScheduler:
    def start(self) -> None:
        """注册 APScheduler job：工作日 9:00-23:00 每小时"""

    def stop(self) -> None

    def run_now(self) -> None:
        """手动触发"""

    def get_status(self) -> dict:
        """返回调度状态、上次运行结果"""
```

---

## 6. API 端点

所有端点在 `api/v1/endpoints/signal_*.py` 中实现，挂载在 `/api/v1/signals` 前缀下。

### 6.1 信号总览

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/events` | GET | 事件列表，query: event_type, market, asset_type, date_from, date_to, limit, offset |
| `/api/v1/signals/events/{id}` | GET | 单事件详情含完整 evidence |
| `/api/v1/signals/stats` | GET | 顶部指标：今日内容数、成功率、覆盖率、失败率 |

### 6.2 采集质量

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/quality/funnel` | GET | 处理漏斗：各 status 的 contents 计数 |
| `/api/v1/signals/quality/creators` | GET | 各 UP 主采集状态：最近采集时间、内容数、成功率 |
| `/api/v1/signals/quality/failures` | GET | 失败原因排行：按 failure_reason 分组计数 |
| `/api/v1/signals/quality/trend` | GET | 内容采集趋势：按日统计，query: days=7 |

### 6.3 内容队列

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/contents` | GET | 内容列表，query: status, display_type, creator_id, limit, offset |
| `/api/v1/signals/contents/{id}` | GET | 单条内容详情含 media、transcript、mentions |
| `/api/v1/signals/contents/{id}/retry` | POST | 重试：将 status 重置为 pending_enrich 或 pending_extract |
| `/api/v1/signals/contents/{id}/ignore` | POST | 标记忽略：status 设为特殊值 ignored |

### 6.4 标的详情

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/assets/{identifier}` | GET | 标的详情：当前事件、mentions 汇总、creators 列表 |
| `/api/v1/signals/assets/{identifier}/mentions` | GET | 该标的所有 mentions（分页、可筛选 sentiment/creator） |
| `/api/v1/signals/assets/{identifier}/timeline` | GET | 信号时间线：按日期排列的 mentions |

identifier 支持 asset_code 或 URL-encoded asset_name。

### 6.5 UP 主管理

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/creators` | GET | UP 主列表，query: is_active, category |
| `/api/v1/signals/creators` | POST | 新增 UP 主 |
| `/api/v1/signals/creators/{id}` | GET | 单个 UP 主详情 |
| `/api/v1/signals/creators/{id}` | PUT | 更新：权重、启用、分类、备注 |
| `/api/v1/signals/creators/{id}/contents` | GET | 该 UP 主最近内容和信号 |

### 6.6 管线控制

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/signals/pipeline/run` | POST | 手动触发管线运行 |
| `/api/v1/signals/pipeline/status` | GET | 调度状态 + 上次运行结果 |
| `/api/v1/signals/pipeline/logs` | GET | 最近运行日志（最近 50 条） |

---

## 7. 前端页面

路由挂在 `/signals` 下，作为 Shell 内的新导航区域。

### 7.1 信号总览 `/signals`

用户每天最先看的页面。

**顶部指标**：今日内容数 / 提取成功率 / UP 主覆盖率 / 失败可解释率

**事件分组**（Tab 或卡片区域）：
- 今日机会
- 今日风险
- 今日分歧
- 今日观察

**事件列表卡片**：
- 标的名称
- 事件类型标签
- 方向（多/空/分歧）
- 评分
- 涉及 UP 主数
- 最高权重 UP 主
- 最新更新时间

**交互**：
- 点击事件进入标的详情
- 按事件类型、市场、标的类型筛选
- 支持只看高权重 UP 主参与的事件

### 7.2 采集质量 `/signals/quality`

**核心区域**：
- 处理漏斗图（collected → pending_enrich → pending_extract → extracted → failed）
- 各 UP 主采集状态表
- 内容形态分布：text / image_text / video_subtitle
- 失败原因排行

**交互**：
- 点击失败原因进入内容队列（自动筛选对应原因）
- 点击某个 UP 主查看其采集记录
- 时间范围筛选

### 7.3 内容队列 `/signals/content`

**列表字段**：
- 发布时间
- UP 主
- 标题或摘要
- 内容形态
- 当前状态
- 失败原因或质量标记
- 是否已产生信号

**操作**：
- 查看原文（跳转 Bilibili）
- 查看提取结果
- 重试
- 标记忽略

**筛选**：status / display_type / creator

### 7.4 标的详情 `/signals/asset/:identifier`

**核心区域**：
- 标的基础信息（名称、代码、类型、市场）
- 当前事件类型标签
- 多空观点比例条
- 涉及 UP 主列表（含权重标识）
- 高权重 UP 主观点高亮

**信号卡片**（每条 mention 一张）：
- UP 主名称和权重
- 内容标题
- 发布时间
- 观点方向
- 置信度
- 原文证据
- 操作建议摘要
- 关键价位
- 原文链接
- 质量标记

**交互**：
- 按 UP 主/观点方向筛选
- 展开原文证据
- 跳转原始内容

### 7.5 UP 主管理 `/signals/creators`

**表格字段**：
- 名称
- 平台
- 是否启用
- 分类
- 人工权重
- 最近采集时间
- 最近提取成功率
- 备注

**操作**：
- 新增
- 启用/停用
- 修改权重
- 修改分类和备注
- 查看该 UP 主最近内容和信号

**权重规则**：
- V1 只支持手动配置
- 权重影响事件排序和评分，但不隐藏相反证据

---

## 8. 调度器集成

在现有调度基础设施中新增信号管线的定时任务：

```
工作日 9:00-23:00，每小时整点：
  SignalPipeline.run(max_contents=50, process_limit=20)
```

管线内部按 collect → enrich → extract → build_events → compute_stats 顺序执行。

每轮运行输出：
- 各步骤开始/结束时间
- 成功/失败/跳过计数
- 失败原因列表
- 总耗时

运行日志保存最近 50 条，供 API 查询。

---

## 9. 里程碑

### M1：采集质量可见（约 1 周）

**目标**：用户能知道系统采集是否正常。

| 编号 | 任务 |
| --- | --- |
| M1.1 | `src/signal/models.py` — content_creators、contents、content_media |
| M1.2 | `src/signal/collector.py` — BilibiliCollector |
| M1.3 | `src/signal/quality.py` — QualityTracker |
| M1.4 | `api/v1/endpoints/signal_creators.py` — UP 主 CRUD |
| M1.5 | `api/v1/endpoints/signal_quality.py` — 采集质量 API |
| M1.6 | 前端 — UP 主管理页 + 采集质量页 |
| M1.7 | config/uploaders.json → content_creators 初始化 |

**验收**：
- UI 维护 UP 主列表（新增/启用/停用/改权重）
- 手动触发采集后看到内容数、覆盖率、失败原因
- 单 UP 主失败不阻塞其他 UP 主

### M2：内容队列可用（约 1 周）

**目标**：用户能看到每条内容的处理状态并介入。

| 编号 | 任务 |
| --- | --- |
| M2.1 | `src/signal/enricher.py` — ContentEnricher |
| M2.2 | models 追加 content_transcripts |
| M2.3 | display_type 映射逻辑 |
| M2.4 | `api/v1/endpoints/signal_content.py` — 内容队列 API |
| M2.5 | 前端 — 内容队列页 |

**验收**：
- 三类形态进入处理流程
- 字幕缺失有质量标记
- 用户可筛选、重试、忽略

### M3：信号看板可用（约 1 周）

**目标**：用户能看到结构化标的信号。

| 编号 | 任务 |
| --- | --- |
| M3.1 | models 追加 signal_mentions |
| M3.2 | `src/signal/extractor/` — 三个提取器 + registry |
| M3.3 | `config/prompts/signal_*.yaml` — 三类 prompt |
| M3.4 | `src/signal/prompt_manager.py` |
| M3.5 | `api/v1/endpoints/signal_overview.py` — 信号总览 API |
| M3.6 | 前端 — 信号总览页（初版） |

**验收**：
- 信号含标的、观点、置信度、证据、来源
- 无操作建议时不编造
- 低质量有标记

### M4：标的详情和事件可用（约 1 周）

**目标**：用户能围绕单个标的做研究。

| 编号 | 任务 |
| --- | --- |
| M4.1 | models 追加 signal_events |
| M4.2 | `src/signal/event_builder.py` |
| M4.3 | 事件评分逻辑 |
| M4.4 | `api/v1/endpoints/signal_asset.py` |
| M4.5 | 信号总览升级为事件列表 |
| M4.6 | 前端 — 标的详情页 + 总览页升级 |

**验收**：
- 多 mention 聚合成事件
- 四类事件区分
- 权重影响排序
- 事件可展开到证据

### M5：管线自动化 + 每日摘要（约 0.5-1 周）

**目标**：自动运行 + 快速复盘。

| 编号 | 任务 |
| --- | --- |
| M5.1 | `src/signal/pipeline.py` |
| M5.2 | `src/signal/scheduler.py` |
| M5.3 | `api/v1/endpoints/signal_pipeline.py` |
| M5.4 | 信号总览增加每日摘要区域 |
| M5.5 | 全链路追溯交互完善 |

**验收**：
- 工作日每小时自动运行
- 可手动触发
- 运行日志可查
- 摘要可追溯到原始内容

---

## 10. V1 明确不做

| 不做 | 留到 |
| --- | --- |
| UnifiedDecisionEngine | V4 |
| 实时信号推送 | V2+ |
| 自动准确率计算和权重调整 | V2+ |
| 综合日报（含技术面/新闻/基本面） | V4 |
| 回测闭环 | V4 |
| 跨资产联动 | V4 |
| 期货代码解析 | V2+ |
| 多平台（小红书/微博） | V3 |
| 持仓集成 | V4+ |
| TradeSignal 镜像写入 | 不再做 |
| 问股集成 | V4 |
| 决策仪表盘 | V4 |

---

## 11. 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| `bili` CLI 不可用 | 采集中断 | enricher 中预留 bilibili-api-python fallback 接口，V1 不主动启用 |
| LLM 幻觉 | 虚假信号 | quality_flags + 未识别代码不进 opportunity |
| Whisper 慢/失败 | 视频信号延迟 | 并发限制 + 超时 + title_only 降级 |
| Vision LLM 不稳定 | 图文信号遗漏 | 降级纯文本 + 质量标记 |
| SQLite 并发 | API 查询阻塞 | WAL 模式 + 批量提交 |
| LLM 成本 | 预算 | 短文本跳过（< 20 字符） + session token 统计 |

---

## 12. 与现有系统的边界

- `src/signal/` 是独立子包，不依赖 `src/services/` 中的现有信号相关服务
- 共享 `src/storage.py` 的 DB 引擎和 session 创建方式，但 signal 模型独立定义在 `src/signal/models.py`
- 共享 `src/config.py` 的 LiteLLM 模型配置
- API 端点挂载到同一个 FastAPI app（`api/app.py`）
- 前端页面加入同一个 React 路由（`apps/dsa-web/src/App.tsx`）
- APScheduler 实例共享，但信号 job 独立注册
- V4 融合时，`src/core/pipeline.py` 通过 `from src.signal import ...` 接入信号数据
