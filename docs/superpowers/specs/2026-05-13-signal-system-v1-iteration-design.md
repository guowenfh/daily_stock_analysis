# 信号系统 V1 迭代 — 设计文档

> **日期**: 2026-05-13
> **状态**: 待审阅
> **前置文档**: `docs/superpowers/specs/2026-05-12-unified-signal-system-v1-design.md` (V1 设计规格)
> **迭代策略**: 在 V1 基础上渐进演化，后端小改 + 前端大改

---

## 1. 迭代目标

在已实现的 V1 信号系统基础上，完成以下改进：

1. **长字幕 2-pass LLM**：超 6000 汉字的视频字幕先摘要再提取，消除信息损失
2. **标的字典校验层**：复用 `stocks.index.json` 自动填充 `asset_code`/`market`
3. **全链路幂等**：提取前检查 + 采集去重加固，确保重跑不产生重复数据
4. **前端产品形态重构**：5 页面 → 简报流 + 研究态侧边栏 + 设置区

### 1.1 不变的部分

- 6 张表结构（无 schema 变更）
- 管线步骤数（collect → enrich → extract → build_events → compute_stats）
- 事件分类逻辑（opportunity / risk / conflict / watch）
- 事件评分因子和权重
- UP 主管理完整 CRUD（含 manual_weight）
- 调度策略（工作日 9-23 点每小时）

### 1.2 不做的事

- 空态设计
- 数据保留策略
- 优先级调度（异动日纯文本优先等）
- 事件聚合阈值校准（T1/T2 基于真实数据分布）
- 事件排序变更（保留 Tab 分区）

---

## 2. 后端变更

### 2.1 长字幕 2-pass LLM

**变更位置**：`src/signal/extractor/video.py` — `VideoSignalExtractor`

**流程**：

```
VideoSignalExtractor.extract(content)
  ├── _get_best_transcript(content) → 获取最佳字幕
  ├── len(transcript) > 6000 汉字？
  │   ├── YES → _summarize_transcript(transcript) → markdown 摘要
  │   │         → 摘要写入 content_transcripts (source=llm_summary, quality=summarized)
  │   │         → 用摘要作为输入调用现有提取流程
  │   │         → 给所有 mentions 加 quality_flag: "based_on_summary"
  │   └── NO  → 直接用原始字幕调用现有提取流程
  └── _apply_quality_rules(mentions)
```

**关键设计决策**：

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 阈值 | 6000 汉字（按字符数） | 约 12000 token，覆盖主流 LLM 上下文窗口 |
| 摘要位置 | 在 VideoSignalExtractor 内部 | 摘要是"字幕太长"的自然解法，属于提取器职责 |
| 摘要缓存 | 写入 content_transcripts 表 | source="llm_summary"，quality="summarized"；重试时可复用 |
| 原始字幕 | 完整保留 | 摘要是额外记录，不替换原文 |

**新增 prompt**：`config/prompts/signal_video_summary.yaml`

摘要 prompt 指导 LLM 保留：
- 标的名称和代码
- 多空观点和论据
- 关键价位
- 操作建议原文

输出为 markdown 格式（保留结构但压缩篇幅）。

**新增质量标记**：`based_on_summary` — 表示信号基于摘要而非原文提取。

**不变的部分**：
- 提取逻辑、prompt 输出 schema、`MentionData` 结构
- 短字幕/无字幕的 `title_only`、`subtitle_missing` 逻辑
- `MAX_TRANSCRIPT_CHARS` 硬截断移除，改为软阈值判定

### 2.2 AssetResolver 标的字典校验层

**新增文件**：`src/signal/asset_resolver.py`

**职责**：提取完成后，对每条 `MentionData` 的 `name`/`code` 尝试与 `stocks.index.json` 匹配，填充或校正 `asset_code`、`market` 字段。

**接口设计**：

```python
class AssetResolver:
    def __init__(self, index_path: str = "stocks.index.json"):
        """加载股票索引，构建 name→code 和 code→info 的查找表"""

    def resolve(self, mentions: list[MentionData]) -> list[MentionData]:
        """批量校验，原地修改 mentions 并返回"""

    def _match_by_code(self, code: str) -> dict | None:
        """按代码精确匹配"""

    def _match_by_name(self, name: str) -> dict | None:
        """按名称匹配：先精确，再前缀，最后模糊"""
```

**匹配策略**：

1. **code 优先**：如果 LLM 返回了 `code`，先按 code 在索引中查找。命中则填充 `asset_code`、`market`。
2. **name 匹配**：如果 code 为空或未命中，按 `name` 查找：
   - 精确匹配（如 "贵州茅台"）
   - 前缀匹配（如 "茅台" → "贵州茅台"）
   - 如果多个匹配，不强行合并，保留原始 name + 打 `name_ambiguous` 标记
3. **未匹配**：保留 LLM 输出的原始 name/code + 打 `code_unresolved` 标记

**调用位置**：`ExtractorRegistry.extract_all()` — 每个内容提取完成后、写入 `signal_mentions` 之前调用 `resolver.resolve(mentions)`。

**不新增**：管线步骤、数据表、`MentionData` 字段。

**未来扩展点（本次不做）**：
- 对接在线股票搜索 API
- 别名表
- "疑似关联" 标记

### 2.3 全链路幂等

**现状**：
- 采集层：`UNIQUE(platform, platform_content_id)` — 已生效
- 事件层：`UNIQUE(asset_name, asset_type, event_date)` + upsert 模式 — 已生效
- 提取层：**缺失** — 崩溃重跑可能产生重复 mentions

**修改方案**：

**提取前检查（主要变更）**：

在 `ExtractorRegistry.extract_all()` 中，对每条 `pending_extract` 内容，先查询 `SignalMention` 表是否已有该 `content_id` 的记录：

```python
existing_mentions = session.query(SignalMention).filter_by(content_id=content.id).count()
if existing_mentions > 0:
    content.status = "extracted"
    result.skipped += 1
    continue
```

**采集层加固**：确认 `BilibiliCollector.fetch_feed()` 的 `IntegrityError` 捕获路径正确计入 `duplicate` 而非 `failed`。

**事件层（不变）**：`SignalEventBuilder.build()` 已是 upsert 模式。

### 2.4 API 排序支持

**变更位置**：`api/v1/endpoints/signal_overview.py`

**新增查询参数**：
- `sort_by`: `score`（默认）| `created_at` | `mention_count`
- `sort_order`: `desc`（默认）| `asc`

**新增 mention 原文数据**：

`api/v1/endpoints/signal_asset.py` — `GET /api/v1/signals/assets/{identifier}/mentions`

- 新增查询参数 `include_content`: `false`（默认）| `true`
- 为 true 时，mention 响应中嵌套 `content_text`（正文）和 `transcript_text`（字幕原文或摘要）

`api/v1/schemas/signal.py` — `MentionResponse` 扩展：
- 新增可选字段 `content_text: str | None`
- 新增可选字段 `transcript_text: str | None`
- 新增可选字段 `summary_text: str | None`（摘要版本，有 based_on_summary 标记时填充）

**向后兼容**：所有新增参数均有默认值，不影响现有调用。

---

## 3. 前端变更

### 3.1 路由重构

| 现有路由 | 新路由 | 说明 |
| --- | --- | --- |
| `/signals` (SignalOverviewPage) | `/signals` (SignalBriefingPage) | 重建：简报流主视图 |
| `/signals/quality` | `/signals/settings?tab=quality` | 收入设置区 |
| `/signals/content` | `/signals/settings?tab=content` | 收入设置区 |
| `/signals/asset/:identifier` | 不再独立路由 | 研究态侧边栏 |
| `/signals/creators` | `/signals/settings?tab=creators` | 收入设置区 |
| — | `/signals/settings` | 新增：设置区入口 |

### 3.2 简报流主视图 (`/signals`)

```
┌─────────────────────────────────────────────────┐
│ 状态条：今日覆盖 X/Y 位创作者 · N 条信号           │
├─────────────────────────────────────────────────┤
│ [全部] [机会] [风险] [分歧] [观察]    ⚙️设置      │
├──────────────────────────────┬──────────────────┤
│                              │                  │
│  信号事件卡片列表              │  研究态侧边栏     │
│  (按 score DESC 排序)        │  (点击卡片展开)    │
│                              │                  │
│  ┌──────────────────────┐   │  标的：贵州茅台    │
│  │ 🟢 机会 | 贵州茅台    │   │  ──────────────  │
│  │ 得分：78.5           │   │  多空比例条       │
│  │ 3位UP主 · 5条提及     │   │                  │
│  │ 最高权重：财经老王     │   │  UP主动态时间线   │
│  └──────────────────────┘   │  ├─ 财经老王      │
│                              │  │  5/13 看多 0.85 │
│  ┌──────────────────────┐   │  │  5/12 看多 0.72 │
│  │ 🔴 风险 | 中国平安    │   │  ├─ 投资张三      │
│  │ 得分：65.2           │   │  │  5/13 看多 0.78 │
│  │ 2位UP主 · 3条提及     │   │                  │
│  └──────────────────────┘   │  原文证据 ▶展开   │
│                              │  操作建议         │
│  ...更多卡片...              │  关键价位         │
└──────────────────────────────┴──────────────────┘
```

**Tab 行为**：
- 机会/风险/分歧/观察 Tab：筛选对应 `event_type`，按 `score DESC` 排序
- 全部 Tab：所有事件混排，按 `score DESC` 排序；卡片上有事件类型标签做视觉区分
- 全部 Tab 可选二级排序：按类型分组（分歧 > 风险 > 机会 > 观察，组内按 score）

**状态条**：
- 文案：`今日覆盖 X/Y 位创作者 · N 条信号 · 最近更新 HH:MM`
- 数据源：`GET /api/v1/signals/stats`（已有）

### 3.3 研究态侧边栏

滑入式面板（右侧，宽度约 400px），点击事件卡片触发。

**内容**：
1. **标的基础信息**：名称、代码、类型、市场
2. **多空比例条**：bullish / bearish / neutral 可视化
3. **UP 主动态时间线**（新增增强）：
   - 以 UP 主为维度聚合
   - 每个 UP 主节点展开后，展示该 UP 主在该标的上的所有发言记录
   - 包含：时间、观点方向、置信度
   - 可看到观点变化轨迹
4. **每条 mention 的详情卡片**：
   - UP 主名称和权重
   - 内容标题
   - 观点方向 + 置信度
   - **原文内容（可展开）**：展示 `Content.text` 或 `ContentTranscript.text`
   - **摘要（可展开）**：有 `based_on_summary` 标记时，展示 `llm_summary` 文本
   - 图片 OCR 文字（图文类型时）
   - 操作建议
   - 关键价位
   - 原文链接（辅助入口）
   - 质量标记

### 3.4 设置区 (`/signals/settings`)

三个 Tab：
- **UP 主管理**：复用现有 `CreatorManagePage` 组件
- **采集质量**：复用现有 `QualityDashboard` 组件
- **内容队列**：复用现有 `ContentQueuePage` 组件

从简报流页面的齿轮图标进入。

### 3.5 组件复用策略

现有页面组件拆为：
- **可复用子组件**：卡片、列表、详情面板、筛选器 → 保留
- **页面壳**：现有 `SignalOverviewPage` 和 `AssetDetailPage` → 废弃
- **降级为子组件**：`CreatorManagePage`、`QualityDashboard`、`ContentQueuePage` → 被设置区复用

---

## 4. 变更文件清单

### 后端

| 文件 | 类型 | 变更说明 |
| --- | --- | --- |
| `src/signal/extractor/video.py` | 修改 | 2-pass LLM：_summarize_transcript() + 阈值判定 + based_on_summary 标记 |
| `src/signal/asset_resolver.py` | **新增** | AssetResolver：stocks.index.json 匹配逻辑 |
| `src/signal/extractor/registry.py` | 修改 | 集成 AssetResolver + 提取前幂等检查 |
| `config/prompts/signal_video_summary.yaml` | **新增** | 视频摘要 prompt 模板 |
| `api/v1/endpoints/signal_overview.py` | 修改 | sort_by/sort_order 查询参数 |
| `api/v1/endpoints/signal_asset.py` | 修改 | include_content 查询参数 |
| `api/v1/schemas/signal.py` | 修改 | MentionResponse 扩展 content_text/transcript_text/summary_text |

### 前端

| 文件 | 类型 | 变更说明 |
| --- | --- | --- |
| `apps/dsa-web/src/App.tsx` | 修改 | 路由变更 |
| `apps/dsa-web/src/components/SidebarNav.tsx` | 修改 | 导航变更 |
| `apps/dsa-web/src/pages/signal/SignalBriefingPage.tsx` | **新增** | 简报流主视图 |
| `apps/dsa-web/src/pages/signal/SignalSettingsPage.tsx` | **新增** | 设置区（Tab 容器） |
| `apps/dsa-web/src/components/signal/ResearchSidebar.tsx` | **新增** | 研究态侧边栏 |
| `apps/dsa-web/src/components/signal/EventCard.tsx` | **新增** | 事件卡片组件 |
| `apps/dsa-web/src/components/signal/StatusBar.tsx` | **新增** | 状态条组件 |
| `apps/dsa-web/src/components/signal/CreatorTimeline.tsx` | **新增** | UP 主动态时间线组件 |
| `apps/dsa-web/src/components/signal/ContentViewer.tsx` | **新增** | 原文/摘要内联查看组件 |
| `apps/dsa-web/src/api/signal.ts` | 修改 | 新参数 + 新响应类型 |
| `apps/dsa-web/src/types/signal.ts` | 修改 | 新类型定义 |

### 测试

| 文件 | 类型 | 变更说明 |
| --- | --- | --- |
| `tests/signal/test_asset_resolver.py` | **新增** | AssetResolver 匹配逻辑测试 |
| `tests/signal/test_extractor.py` | 修改 | 2-pass LLM 摘要 + 提取测试用例 |
| `tests/signal/test_pipeline.py` | 修改 | 幂等性测试用例 |

---

## 5. 兼容性与风险

### 向后兼容

- 表结构无变更，零迁移成本
- `content_transcripts` 新增 `source="llm_summary"` 记录，不需要 schema 变更
- `quality_flags` 新增 `based_on_summary` 值，不需要 schema 变更
- 所有新 API 参数有默认值，不影响现有调用

### 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 摘要 LLM 丢失关键标的信息 | 信号遗漏 | prompt 模板要求保留标的名称/代码/观点/价位；based_on_summary 标记让用户可追溯 |
| AssetResolver 前缀匹配误命中 | 标的归并错误 | 多匹配时不合并 + name_ambiguous 标记 |
| 前端重构影响现有页面 | 功能回归 | 设置区复用现有组件而非重写；旧路由重定向到新路由 |
| stocks.index.json 不完整 | 校验漏报 | 未匹配打 code_unresolved 标记，不阻塞流程 |

---

## 6. 与 V1 设计文档的关系

本文档是 `2026-05-12-unified-signal-system-v1-design.md` 的增量迭代，不替代原文档。

原文档中的以下内容保持不变：
- §2 架构决策
- §3 主链路（5 步）
- §4 数据模型（6 张表）
- §5 模块职责（除 video.py 和 registry.py 的变更外）
- §6 API 端点（仅追加参数）
- §8 调度器集成
- §10 V1 明确不做
- §11 风险（新增摘要相关条目）
- §12 与现有系统的边界
