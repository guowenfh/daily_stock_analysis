# 统一信号系统技术决策交接文档

> 日期：2026-05-11  
> 状态：草案  
> 文档定位：当前分支技术决策事实交接  
> 目标读者：新技术团队、产品、架构、后端、前端、测试  
> 对齐目标：`docs/superpowers/specs/2026-05-10-unified-signal-system-technical-prd.md`

---

## 1. 文档目的

本文档用于总结当前分支相对 `main` 分支，在“统一信号系统”方向上已经尝试过的技术决策。

它不是新的产品 PRD，也不是要求新团队照搬当前实现。当前分支中已经存在大量 Bilibili 信号、字幕、调度、聚合、API、前端页面和历史文档实现，但这些实现并未形成一条稳定、清晰、可维护的主链路。

因此本文档只做三件事：

- 基于代码事实说明“已经做过什么”。
- 标注哪些设计方向值得继承，哪些需要谨慎，哪些建议重做。
- 帮助新团队在新分支中少走弯路。

判断口径：

| 标记 | 含义 |
| --- | --- |
| 建议继承 | 方向正确，可作为新实现的基础思路 |
| 谨慎继承 | 有价值，但当前实现方式需要收敛或重构 |
| 建议重做 | 当前实现混乱、重复或偏离 V1，需要重新设计 |

---

## 2. 总体链路事实

当前分支围绕 Bilibili 内容到信号做过一条完整但较分散的链路：

```text
UP 主配置
  -> Bilibili 动态/视频采集
  -> 内容入库
  -> 字幕获取或音频转录
  -> 按内容类型选择提取器
  -> LLM 提取结构化 mentions
  -> 写入 StockMention / TradeSignal
  -> 聚合 SignalEvent / ConsensusResult
  -> API 和 Web 页面展示
  -> Scheduler 定时运行
```

核心代码事实：

- `src/services/dynamics_service.py`：Bilibili 动态采集主路径。
- `src/services/bilibili_signal_pipeline.py`：采集、字幕、提取、共识的串联服务。
- `src/services/extractors/`：按内容类型拆分的信号提取器。
- `config/prompts/bilibili_signal.yaml`：Bilibili 信号提取 prompt。
- `src/storage.py`：平台无关内容、信号、事件、权重等模型集中定义。
- `api/v1/endpoints/bilibili_signals.py`、`api/v1/endpoints/uploaders.py`、`api/v1/endpoints/scheduler.py` 等：当前分支暴露的 API。
- `apps/dsa-web/src/pages/`：当前分支新增的信号、UP 主、调度、共识等页面。

交接结论：

- “内容采集 -> 标准化 -> 提取 -> 标的事实层 -> 单标的事件 -> 前端看板”这个方向建议继承。
- 当前分支的问题主要是模块太多、链路重复、命名不统一、V1/V2/V4 能力混在一起。
- 新实现应先收敛到 PRD 的 V1：Bilibili、三类内容形态、单标的事件、人工 UP 主权重、采集质量和信号看板。

---

## 3. UP 主配置与权重

### 3.1 代码事实

当前分支使用 `config/uploaders.json` 维护 Bilibili UP 主配置，内容包括：

- `uid`
- `name`
- `category`
- `is_active`
- `fetch_interval_min`
- `priority`

该配置分为：

- `key_uploaders`
- `filter_uploaders`

`src/services/uploader_signal_config_service.py` 会读取 `config/uploaders.json`，同步到 `UploaderSignalConfig`：

- `priority=1` 映射为较高基础权重。
- `priority=2` 映射为默认权重。
- `priority=3` 映射为较低权重。
- 同时写入分类、启用状态、市场范围和资产范围。

当前实现还包含历史准确率修正：

- `historical_accuracy_adjustment()` 会读取 `TradeSignal` 和 `SignalVerification`。
- 样本数少于 8 时不修正。
- 修正范围限制在 `0.85-1.15`。

### 3.2 决策含义

当前分支已经确认了一个有价值的产品方向：UP 主不是同权重的，用户需要通过配置表达自己对不同 UP 主的信任度。

同时也尝试了一个更复杂的方向：基于历史验证结果自动修正权重。

### 3.3 继承建议

谨慎继承。

建议继承：

- UP 主列表配置。
- 启用/停用。
- 分类。
- 抓取间隔。
- 人工权重或优先级。

V1 建议暂缓：

- 自动历史准确率修正。
- 自动权重调整。
- 过早引入市场范围、资产范围的复杂配置。

### 3.4 新实现建议

新团队应把 UP 主配置做成 V1 的基础能力：

- 用户可以维护 Bilibili UP 主。
- 用户可以手动配置权重。
- 系统排序和事件评分体现权重。
- 所有证据仍完整展示，权重不能隐藏相反观点。

不要在 V1 自动修改权重。历史表现可以作为后续参考指标展示，但不参与自动计算。

---

## 4. Bilibili 数据获取

### 4.1 动态采集

代码事实：

`src/services/dynamics_service.py` 使用 `bili feed --yaml` 作为 Bilibili 动态时间线主数据源。

当前实现特征：

- 通过 `subprocess.run(["bili", "feed", "--yaml"])` 调用本地 `bili` CLI。
- YAML 输出通过 `yaml.safe_load()` 解析。
- 支持最多 3 次重试。
- 单次命令超时为 60 秒。
- 使用 `data/dynamics_state.json` 保存已处理动态 ID。
- 从动态 item 中解析：
  - 动态 ID。
  - 作者 UID。
  - 作者名称。
  - 动态类型。
  - 标题。
  - 文本。
  - URL。
  - 图片。
  - 视频 BV 号。
  - 发布时间。
  - 点赞、评论、转发等统计。

动态类型映射：

| Bilibili 动态类型 | 当前内容类型 |
| --- | --- |
| `MAJOR_TYPE_ARCHIVE` | `video` |
| `MAJOR_TYPE_COMMON` | `article` |
| `MAJOR_TYPE_OPUS` | `article` |
| `MAJOR_TYPE_DRAW` | `article` |

过滤策略：

- 优先按 UID 匹配 `ContentCreator.platform_uid`。
- UID 不匹配时按 UP 主名称匹配。
- 非关注 UP 主动态跳过。

入库策略：

- 内容写入 `Content`。
- 图片写入 `ContentMedia(media_type=image)`。
- 视频写入 `ContentMedia(media_type=video)`。
- 原始载荷写入 `Content.raw_json`。

### 4.2 视频列表采集

代码事实：

`src/services/bilibili_fetcher_service.py` 使用 `bili user-videos <uid> --max <n> --yaml` 拉取 UP 主视频列表。

它与 `DynamicsService` 是另一条采集路径，主要字段包括：

- BV 号。
- 标题。
- 简介。
- 时长。
- 播放、点赞、投币、收藏、分享、弹幕。
- 作者 UID。
- 发布时间。
- 封面。
- 字幕。

### 4.3 Bilibili API 备用方案

代码事实：

`src/services/bilibili_api_service.py` 使用 `bilibili-api-python` 作为备用方案。

当前实现包括：

- 获取 UP 主视频列表。
- 获取视频详情。
- 获取字幕列表并下载字幕内容。
- 获取用户动态。

但该库是可选依赖，代码中通过 `try import` 判断是否可用。需要登录态或 Cookie 的接口稳定性取决于环境配置。

### 4.4 决策含义

当前分支做出了一个实际有效的方向选择：优先使用本地 `bili` CLI，降低直接维护 Bilibili HTTP API、Cookie、签名和登录态的复杂度。

同时，当前实现存在采集入口重复：

- 动态采集一条链路。
- 视频列表采集一条链路。
- API 备用又是一条链路。

这会导致去重、字段归一、字幕获取、错误处理分散。

### 4.5 继承建议

建议继承 `bili CLI 优先`。

谨慎继承多入口采集。

建议新实现：

- 保留 `bili feed --yaml` 作为 V1 主采集入口。
- 视频列表采集作为补充能力，不作为另一套主链路。
- `bilibili-api-python` 只作为字幕或详情补全 fallback，不作为第一阶段主路径。
- 动态、视频、专栏最终都进入统一内容模型。

### 4.6 新实现建议

新团队应设计一个统一的 Bilibili 采集服务：

```text
BilibiliCollector
  -> fetch_feed()
  -> parse_items()
  -> normalize_content_shape()
  -> save_content()
  -> enqueue_enrichment()
```

采集服务需要对用户可见地输出：

- 本轮扫描内容数。
- 新增内容数。
- 重复内容数。
- 跳过内容数。
- 失败内容数。
- UP 主覆盖率。
- 失败原因。

---

## 5. 内容标准化

### 5.1 代码事实

当前分支在 `src/storage.py` 中定义了平台无关内容模型：

- `ContentCreator`
- `Content`
- `ContentMedia`
- `ContentTranscript`

`Platform` 枚举已经预留：

- `bilibili`
- `youtube`
- `weibo`
- `xiaohongshu`
- `twitter`
- `wechat_mp`
- `douyin`
- `tiktok`

`ContentType` 枚举包括：

- `video`
- `article`
- `dynamic`
- `image`
- `live`
- `short_video`
- `forward`

当前采集侧并没有完全按 PRD 中的三类内容形态收敛，而是保留了较多平台/实现相关类型。

### 5.2 决策含义

当前分支已经意识到后续会有多平台，因此尝试建立平台无关内容层。

但对 V1 来说，类型过多会增加提取器、前端筛选和状态处理复杂度。

### 5.3 继承建议

谨慎继承。

建议继承：

- 平台无关内容思想。
- 内容和媒体分离。
- 原始载荷保留。
- 平台内容 ID 保留。

建议收敛：

- V1 产品形态只暴露 `纯文本 / 图文 / 视频与视频字幕`。
- 内部可以保留 `dynamic / article / image / video / forward`，但必须映射到 PRD 三类内容形态。

### 5.4 新实现建议

新团队应在产品层固定三类内容形态：

| PRD 内容形态 | 当前实现可映射类型 |
| --- | --- |
| 纯文本 | `dynamic`、无图片短 `article`、转发评论 |
| 图文 | `image`、带图片动态、专栏、长文 |
| 视频与视频字幕 | `video` |

前端、提取成功率、内容队列和失败原因都应围绕这三类形态展示。

---

## 6. 字幕获取与音频转录

### 6.1 代码事实

当前分支有多套字幕/转录实现：

- `src/services/audio_transcription_service.py`
- `src/services/whisper_subtitle_service.py`
- `src/services/bilibili_fetcher_service.py` 中的字幕 fallback。
- `src/services/bilibili_signal_pipeline.py` 中的批量字幕预获取。

已尝试的字幕链路：

```text
已有字幕
  -> Bilibili 字幕/API
  -> bili audio 下载音频
  -> Whisper 本地转录
  -> 保存 subtitle / subtitle_raw / has_subtitle
```

`WhisperSubtitleService` 事实：

- `bili video <bvid> --subtitle --yaml` 获取平台字幕。
- `bili audio <bvid> -o <temp_dir>` 下载音频。
- `whisper <audio> --model turbo --language zh --output_format json` 转录。
- 转录结果保留 segments，可转纯文本，也可转 JSON。
- 默认临时目录为 `/tmp/whisper_subtitles`。
- Whisper 超时最长 30 分钟。

`AudioTranscriptionService` 事实：

- 使用 `bili audio <bvid> --no-split -o <temp_dir>` 下载完整音频。
- 使用 `whisper --model turbo --output_format txt --language zh` 生成纯文本。
- 默认临时目录为系统 temp 下的 `openclaw`。
- 使用类变量限制同一时间只有一个转录任务。
- 若已有字幕超过 100 字符，直接复用。

`BilibiliSignalPipeline._fetch_subtitles_for_videos()` 事实：

- 查询 Bilibili video 且 `has_subtitle == False` 的内容。
- 优先通过 `BilibiliApiService.get_video_detail()` 获取字幕。
- 失败后使用 `WhisperSubtitleService` 下载音频和转录。
- 字幕长度达到 50 字符才认为有效。
- 使用 `SIGALRM` 对 Whisper fallback 加 300 秒超时保护。

### 6.2 决策含义

当前分支确认了一个重要结论：视频内容不能只依赖标题，字幕/转录是视频信号质量的关键。

同时，当前实现存在明显重复：

- 两套下载音频逻辑。
- 两套 Whisper 调用逻辑。
- 两套临时目录。
- 纯文本和分段 JSON 两种输出混用。
- 字幕获取有 API、CLI、pipeline 内部 fallback 多个入口。

### 6.3 继承建议

建议继承字幕策略：

- 已有字幕优先。
- 平台字幕其次。
- 音频转录兜底。
- 字幕缺失时降低信号置信度。

建议重做实现：

- 合并为一个统一字幕服务。
- 统一音频下载目录、缓存策略、超时、并发限制和日志。
- 明确字幕来源：平台字幕、Whisper、人工补录。
- 明确字幕质量：长度不足、仅标题、转录失败。

### 6.4 新实现建议

新团队应把字幕处理作为“内容补全”能力，而不是散落在提取器或 pipeline 内部。

推荐产品链路：

```text
视频内容入库
  -> 字幕补全任务
  -> 平台字幕尝试
  -> Whisper 兜底
  -> 写入字幕文本和字幕质量标记
  -> 进入信号提取队列
```

前端需要展示：

- 有字幕。
- 无字幕，仅标题。
- Whisper 转录成功。
- Whisper 转录失败。
- 字幕过短。

---

## 7. Prompt 与信号提取

### 7.1 Prompt 配置事实

当前分支将 Bilibili 信号 prompt 放在：

`config/prompts/bilibili_signal.yaml`

模板按内容类型拆分：

- `dynamic`
- `image`
- `video`

共同输出要求：

- 必须返回 JSON。
- 顶层包含：
  - `sentiment`
  - `confidence`
  - `mentions`
  - `key_levels`
  - `trade_advice`
  - `market_view`
- `mentions` 中包含：
  - `code`
  - `name`
  - `asset_type`
  - `market`
  - `sentiment`
  - `confidence`
  - `reasoning`
  - `uploader_attitude`
  - `trade_advice`
  - `market_view`
  - `is_primary`
  - `key_levels`

Prompt 的核心倾向是“宁多勿少”：

- 内容中出现的每一个股票、代码、板块、ETF、指数都必须提取。
- 顺带提及也要提取，用 `is_primary=false` 标记。
- 只有代码没有名称也要提取。
- 只有名称没有代码也要提取。
- 标题中出现的股票也要提取。

视频 prompt 额外强调：

- 先从标题提取。
- 再从字幕逐行扫描。
- 操作建议必须基于 UP 主原话。
- 不能因为标题提到某只股票就生成买入/卖出建议。

图文 prompt 强调：

- 图片中的 K 线图、持仓截图、板块热力图、资金流向。
- 图片文字和数字准确识别。
- 文字和图片综合判断。

### 7.2 提取器事实

当前分支在 `src/services/extractors/` 下实现了按内容类型注册的提取器：

- `TextSignalExtractor`
- `ImageSignalExtractor`
- `VideoSignalExtractor`
- `ForwardExtractor`
- `ExtractorRegistry`

`PromptManager` 从 YAML 加载模板，根据 `ContentType.value` 渲染。

文本提取器：

- 处理 `dynamic` 和 `article`。
- 文本少于 20 字符跳过。
- 使用 LiteLLM 调用 `cfg.litellm_model`。
- `max_tokens=8192`，`temperature=0.3`。
- 支持从 markdown code block 或文本中提取 JSON。
- 推理模型无 `content` 时尝试读取 `reasoning_content`。

图文提取器：

- 处理 `image`。
- 使用 Vision LLM。
- 最多传 10 张图片。
- Vision 模型优先级：配置的 vision model、OpenAI vision model、LiteLLM model、Gemini、Anthropic、OpenAI。
- `max_tokens=8192`，`temperature=0.3`，timeout 120 秒。

视频提取器：

- 处理 `video`。
- 链路为：字幕 -> 音频转录 -> 标题 fallback。
- 若字幕/转录少于 50 字符，会尝试用标题和正文作为 fallback。
- 视频 LLM `temperature=0.2`。

转发提取器：

- 若有 `forward_source`，递归处理原始内容。
- 同时分析转发评论中的额外信号。

### 7.3 决策含义

当前分支做对了三件事：

- 提取器按内容形态扩展，而不是把所有平台逻辑写死在一个函数中。
- Prompt 外置到 YAML，便于迭代。
- 输出结构已经接近 PRD 所需的“标的、观点、证据、建议、关键价位、置信度”。

主要问题：

- Prompt 仍然强 Bilibili 绑定。
- “宁多勿少”容易引入低质量 mentions，需要配套质量标记和事件筛选。
- 标题 fallback 可能导致视频被过度解读。
- 资产类型已经扩展到期货、商品，但 V1 PRD 暂不做跨资产联动。

### 7.4 继承建议

建议继承：

- 按内容形态拆 prompt。
- Prompt 配置外置。
- JSON 输出契约。
- `mentions` 作为基础事实输出。
- `is_primary` 区分主标的和顺带提及。

谨慎继承：

- “宁多勿少”策略。
- 标题 fallback。
- 期货、商品等超出 V1 的资产类型。

### 7.5 新实现建议

新团队应将 prompt 从“Bilibili prompt”升级为“内容形态 prompt”：

- 文本 prompt。
- 图文 prompt。
- 视频字幕 prompt。

Bilibili 只是来源平台，不应进入核心提取策略。

同时需要明确质量规则：

- 仅标题提取的信号必须低置信。
- 无原文操作建议时不得生成操作建议。
- 未识别代码的标的可以保留，但不能进入高置信事件。
- 顺带提及进入 mention，但默认不直接推动 opportunity。

---

## 8. 信号事实层与事件聚合

### 8.1 信号事实层代码事实

当前分支在 `src/storage.py` 中定义了两层信号相关模型：

- `StockMention`
- `TradeSignal`

`BilibiliSignalPipeline._store_extraction_result()` 会对每个 mention 同时写：

- 一条 `TradeSignal`。
- 一条 `StockMention`。

当前文档 `docs/BILIBILI_PIPELINE.md` 已明确写过：

- `StockMention` 是 B站信号事实源。
- `TradeSignal` 作为兼容旧接口和历史验证脚本的镜像数据继续写入。
- 新聚合、事件榜和时间线优先读取 `StockMention JOIN Content JOIN ContentCreator`。

`StockMention` 保存的信息包括：

- 内容 ID。
- 信号 ID。
- 平台。
- 股票代码和名称。
- 市场。
- mention 类型。
- asset_type。
- sentiment。
- confidence。
- reasoning。
- uploader_attitude。
- key_levels。
- trade_advice。
- market_view。
- is_primary。

### 8.2 事件聚合代码事实

`src/services/bilibili_signal_event_service.py` 从 `StockMention` 构建 `SignalEvent`。

当前事件类型：

- `opportunity`
- `exit_risk`
- `conflict`
- `watch`

核心资产范围：

- `stock`
- `etf`
- `index`
- `sector`

评分因子：

- sentiment。
- confidence。
- UP 主权重。
- UP 主数量。
- 是否有 trade_advice。
- bullish / bearish 分歧比例。
- 风险关键词，如“风险、减仓、卖、止损、回避”。

事件证据保存在 `evidence_json`，包括：

- mention ID。
- content ID。
- uploader ID。
- uploader name。
- content type。
- title。
- summary。
- sentiment。
- confidence。
- weight。
- reasoning。
- trade advice。
- source URL。
- published time。

### 8.3 共识引擎代码事实

`src/services/consensus_engine.py` 是更早或更复杂的共识分析引擎。

它会按股票聚合 `TradeSignal`，计算：

- bullish / bearish / neutral 数量。
- 共识类型。
- 置信度。
- 支撑/压力。
- 提到的 UP 主。
- 关键观点。
- 加权得分。
- UP 主权重明细。

它还包含硬编码的高优先级 UP 主权重和历史准确率方向。

### 8.4 决策含义

当前分支已经摸索出一个重要分层：

```text
StockMention = 原子事实
SignalEvent = 面向用户的单标的事件
ConsensusResult = 更复杂的共识分析结果
```

这与 PRD 的 V1 更接近的是：

```text
单条信号 -> 单标的事件 -> 前端展示
```

而不是完整交易决策系统。

### 8.5 继承建议

建议继承：

- `StockMention` 作为原子事实层。
- `SignalEvent` 作为前端事件层。
- 事件必须保留 evidence。
- 事件支持机会、风险、分歧、观察。

谨慎继承：

- `TradeSignal` 镜像。
- `ConsensusEngine` 的复杂共识。
- 历史准确率参与权重。

建议新实现中：

- V1 只保留单标的事件。
- 不做跨资产联动。
- 不做自动准确率修正。
- 不把复杂共识作为主链路。

---

## 9. 调度任务

### 9.1 代码事实

当前分支存在多套调度相关实现：

- `src/services/scheduler_service.py`
- `src/services/signal_scheduler.py`
- `src/services/unified_scheduler.py`
- `api/v1/endpoints/scheduler.py`
- `deploy/stockclaw-scheduler.service`
- `docs/SCHEDULER_INTEGRATION.md`

`SchedulerService` 使用 APScheduler：

- `BackgroundScheduler`
- `IntervalTrigger`
- `CronTrigger`

默认间隔：

- 60 分钟。

日志：

- 保存到 `data/scheduler_log.json`。
- 只保留最近 100 条。

当前 `SchedulerService.run_daily_pipeline_job()` 串联：

```text
BilibiliSignalPipeline.run(max_dynamics=50, process_limit=20)
  -> dynamics_saved
  -> signals_extracted
  -> consensus_stocks
  -> success / errors
```

CLI 能力：

- `--start`
- `--run`
- `--status`
- `--interval`
- `--debug`

API 能力：

- 查看 scheduler 状态。
- 启动。
- 停止。
- 立即运行。
- 查看日志。
- 更新配置。

### 9.2 决策含义

当前分支已经确认调度能力需要具备：

- 手动触发。
- 定时触发。
- 状态查询。
- 执行日志。
- 失败不应完全黑盒。

但当前调度入口过多，容易导致重复执行、状态不一致和排障困难。

### 9.3 继承建议

建议继承：

- APScheduler 作为进程内调度方案。
- `run_now` 手动触发。
- scheduler 状态和日志。
- 每轮任务输出统计。

建议重做：

- 合并多套 scheduler。
- 明确只有一个信号系统调度入口。
- 将采集、补全、提取、事件生成拆成可观测步骤。

### 9.4 新实现建议

V1 调度应按 PRD 主链路表达：

```text
collect_contents
  -> enrich_contents
  -> extract_signals
  -> build_events
  -> update_daily_summary
```

每一步都应输出：

- 开始时间。
- 结束时间。
- 成功数。
- 失败数。
- 跳过数。
- 失败原因。

前端采集质量页应直接消费这些统计。

---

## 10. API 与前端页面

### 10.1 API 代码事实

当前分支新增了多组 API：

- `/api/v1/uploaders`
- `/api/v1/bilibili-signals`
- `/api/v1/signal-collection`
- `/api/v1/dashboard`
- `/api/v1/accuracy`
- `/api/v1/scheduler`
- `/api/v1/consensus`
- `/api/v1/extraction`
- `/api/v1/uploader-summary`

`api/v1/endpoints/bilibili_signals.py` 提供了大量能力：

- 信号列表。
- 按标的聚合。
- 按 UP 主聚合。
- signal events。
- 标的 timeline。
- mentions 列表。
- UP 主 review。
- 单条信号详情。

`api/v1/endpoints/extraction.py` 提供：

- 提取 session 列表。
- session 详情。
- 单条内容提取日志。
- UP 主提取统计。

`api/v1/endpoints/scheduler.py` 提供：

- scheduler 状态。
- 启动。
- 停止。
- 立即执行。
- 日志。
- 配置更新。

### 10.2 前端代码事实

当前分支在 `apps/dsa-web/src/App.tsx` 增加了多条路由：

- `/uploaders`
- `/uploader-summary`
- `/bilibili-signals`
- `/scheduler`
- `/accuracy`
- `/extraction-history`
- `/consensus`

相关页面：

- `UploadersPage.tsx`
- `UploaderSummaryPage.tsx`
- `BilibiliSignalsPage.tsx`
- `SchedulerPage.tsx`
- `AccuracyPage.tsx`
- `ExtractionHistoryPage.tsx`
- `ConsensusPage.tsx`

`BilibiliSignalsPage.tsx` 当前承载了较多能力：

- 事件卡片。
- 机会、风险、观察、分歧筛选。
- 市场和内容类型筛选。
- 标的时间线抽屉。
- UP 主聚合卡片。
- UP 主 review。
- 原文链接。
- 证据展示。

`UploaderSummaryPage.tsx` 以 UP 主为维度展示：

- 总信号数。
- 看多 / 看空 / 中性数量。
- 看多股票。
- 看空股票。
- 理由摘要。
- 时间范围筛选。

### 10.3 决策含义

当前分支已经验证了前端需要至少覆盖两类视角：

- 标的视角：今天哪些标的形成机会、风险、分歧。
- UP 主视角：每个 UP 主近期提到了哪些标的，偏多还是偏空。

但页面拆分已经偏技术实现和历史功能堆叠，不完全符合新 PRD 的产品信息架构。

### 10.4 继承建议

谨慎继承。

建议继承的页面能力：

- 信号事件列表。
- 标的时间线。
- 原文证据。
- UP 主维度聚合。
- 提取日志。
- 调度状态。

建议重做页面信息架构：

```text
信号总览
采集质量
内容队列
标的详情
UP 主管理
```

当前页面中的能力应被重新归位，而不是照搬现有路由。

### 10.5 新实现建议

新团队实现前端时，优先围绕用户使用路径设计：

- 用户每天先看“信号总览”。
- 采集异常时进入“采集质量”和“内容队列”。
- 对某个标的感兴趣时进入“标的详情”。
- 需要调整信任度时进入“UP 主管理”。

不建议 V1 单独暴露 accuracy、consensus、scheduler、extraction-history 为顶层主导航。它们可以作为采集质量或系统状态下的子视图。

---

## 11. 当前分支中的主要风险

### 11.1 主链路重复

代码中同时存在：

- `DynamicsService`
- `BilibiliFetcherService`
- `BilibiliApiService`
- `BilibiliSignalPipeline`
- `SignalCollectionScheduler`
- `SchedulerService`
- `UnifiedScheduler`

这些模块都与采集、补全、提取或调度有关，但边界并不清晰。

新实现应先定义唯一主链路，再补扩展点。

### 11.2 V1 和后续阶段混在一起

当前分支包含：

- accuracy。
- backtest。
- consensus deep analysis。
- daily advisor。
- RAG。
- notifications。
- verification scheduler。

这些能力不是 PRD V1 的重点。新团队应避免把这些模块带入第一阶段。

### 11.3 Bilibili 强绑定

虽然 `storage.py` 中有平台枚举和平台无关内容模型，但 prompt、API、页面、服务名大量绑定 Bilibili。

新实现应做到：

- 采集层绑定平台。
- 内容形态、提取、信号、事件尽量平台无关。

### 11.4 信号质量规则不足

当前实现会降低“视频无字幕”的 confidence，但整体质量状态仍不够产品化。

新实现需要明确：

- 仅标题提取。
- 字幕缺失。
- 图片无法识别。
- 标的未解析。
- LLM JSON 非法。
- 无原文操作建议。

这些都应进入内容队列或质量标记。

### 11.5 事件类型命名不一致

PRD 使用：

- 机会。
- 风险。
- 分歧。
- 观察。

当前代码事件类型为：

- `opportunity`
- `exit_risk`
- `conflict`
- `watch`

新实现需要统一产品命名和内部枚举，避免前后端各自翻译。

---

## 12. 新团队建议继承清单

建议继承：

- 使用 `bili CLI` 作为 Bilibili V1 主数据源。
- 保留平台原始载荷，所有内容可追溯到原文。
- 内容先标准化，再进入提取。
- 视频必须优先使用字幕或转录，不应只看标题。
- Prompt 按内容形态拆分。
- 提取结果以 `mentions` 为原子事实。
- 事件必须能展开底层证据。
- UP 主人工权重影响排序但不覆盖证据。
- 调度任务需要手动触发、定时触发、状态和日志。

谨慎继承：

- 多套 Bilibili 采集入口。
- 多套字幕/转录服务。
- `TradeSignal` 兼容镜像。
- 历史准确率自动修正。
- 复杂共识引擎。
- accuracy、verification、backtest 等后续能力。

建议重做：

- 统一 Bilibili 采集服务。
- 统一内容补全服务。
- 统一信号系统调度器。
- 面向 PRD 五个页面重做前端信息架构。
- 将 prompt 从 Bilibili 绑定改为内容形态驱动。
- 将失败原因和质量标记产品化。

---

## 13. 对新实现的落地顺序建议

### M1：采集与 UP 主配置

吸收当前：

- `config/uploaders.json`
- `DynamicsService` 中 `bili feed --yaml`
- `ContentCreator` / `Content` / `ContentMedia` 的建模思路

避免带入：

- 视频列表单独主链路。
- 多 scheduler。
- 自动权重修正。

### M2：内容补全

吸收当前：

- 平台字幕优先。
- Whisper 兜底。
- 字幕长度阈值。
- 单任务转录并发保护。

重做：

- 合并字幕服务。
- 统一质量标记。
- 将补全状态展示到内容队列。

### M3：信号提取

吸收当前：

- `dynamic / image / video` prompt 思路。
- JSON 输出。
- `mentions` 字段结构。
- `ExtractorRegistry` 的扩展方向。

重做：

- 平台无关 prompt 命名。
- 低置信规则。
- 标题 fallback 的降级策略。

### M4：事件与前端

吸收当前：

- `StockMention -> SignalEvent`。
- evidence 展开。
- 标的 timeline。
- UP 主聚合视角。

重做：

- 按 PRD 五个页面组织前端。
- V1 只做单标的事件。
- 暂缓完整共识和准确率体系。

---

## 14. 代码事实索引

本节列出本文档主要依据的当前分支文件，便于新团队继续核对。

| 主题 | 文件 |
| --- | --- |
| PRD 目标 | `docs/superpowers/specs/2026-05-10-unified-signal-system-technical-prd.md` |
| Bilibili 动态采集 | `src/services/dynamics_service.py` |
| Bilibili 视频采集 | `src/services/bilibili_fetcher_service.py` |
| Bilibili API fallback | `src/services/bilibili_api_service.py` |
| 信号 pipeline | `src/services/bilibili_signal_pipeline.py` |
| 字幕与 Whisper | `src/services/whisper_subtitle_service.py` |
| 音频转录 | `src/services/audio_transcription_service.py` |
| Prompt 配置 | `config/prompts/bilibili_signal.yaml` |
| Prompt 管理 | `src/services/prompt_manager.py` |
| 提取器基础类型 | `src/services/extractors/base.py` |
| 文本提取 | `src/services/extractors/text_extractor.py` |
| 图文提取 | `src/services/extractors/image_extractor.py` |
| 视频提取 | `src/services/extractors/video_extractor.py` |
| 转发提取 | `src/services/extractors/forward_extractor.py` |
| 内容与信号模型 | `src/storage.py` |
| UP 主权重 | `src/services/uploader_signal_config_service.py` |
| 信号事件 | `src/services/bilibili_signal_event_service.py` |
| 共识引擎 | `src/services/consensus_engine.py` |
| 调度服务 | `src/services/scheduler_service.py` |
| 信号采集调度 | `src/services/signal_scheduler.py` |
| Bilibili 信号 API | `api/v1/endpoints/bilibili_signals.py` |
| UP 主 API | `api/v1/endpoints/uploaders.py` |
| 调度 API | `api/v1/endpoints/scheduler.py` |
| 提取历史 API | `api/v1/endpoints/extraction.py` |
| Web 路由 | `apps/dsa-web/src/App.tsx` |
| Bilibili 信号页面 | `apps/dsa-web/src/pages/BilibiliSignalsPage.tsx` |
| UP 主汇总页面 | `apps/dsa-web/src/pages/UploaderSummaryPage.tsx` |
| 历史管线文档 | `docs/BILIBILI_PIPELINE.md` |
| 调度历史文档 | `docs/SCHEDULER_INTEGRATION.md` |
| 字幕修复历史文档 | `docs/FIX_DYNAMIC_ID_AND_AUDIO_TRANSCRIPTION.md` |

---

## 15. 最终交接结论

当前分支最有价值的不是代码本身，而是已经验证过这些方向：

- Bilibili V1 可以优先依赖 `bili CLI`。
- 视频信号质量依赖字幕和转录。
- 信号提取应该按内容形态扩展。
- 原子事实层应该是“某内容中某 UP 主提到某标的”的 mention。
- 前端必须能从事件追溯到证据。
- 调度和失败原因必须可见。

新实现不应从当前分支整体迁移，而应按 PRD 重新实现一条更干净的 V1 主链路：

```text
Bilibili 内容采集
  -> 内容标准化
  -> 内容补全
  -> 信号提取
  -> 单标的事件
  -> 采集质量 / 内容队列 / 信号总览 / 标的详情 / UP 主管理
```

当前分支中的实现应作为经验库和反例库，而不是作为直接复制的工程基线。
