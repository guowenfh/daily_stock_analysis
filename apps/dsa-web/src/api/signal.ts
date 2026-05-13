import apiClient from './index';
import type { ParsedApiError } from './error';
import type {
  Creator,
  CreatorCreate,
  CreatorUpdate,
  QualityStats,
  FunnelData,
  FailureItem,
  CreatorStats,
  ContentItem,
  Mention,
  SignalEvent,
  AssetDetailOverview,
  PipelineStatus,
  PipelineProgress,
  EventListParams,
  MentionListParams,
} from '../types/signal';

const BASE = '/api/v1/signals';

/** FastAPI JSON uses snake_case; map to app camelCase types. */
type CreatorSnake = {
  id: number;
  platform: string;
  platform_uid: string;
  name: string;
  category: string | null;
  is_active: boolean;
  manual_weight: number;
  fetch_interval_min: number;
  notes: string | null;
  last_fetch_at: string | null;
  created_at: string | null;
};

function mapCreator(raw: CreatorSnake): Creator {
  return {
    id: raw.id,
    platform: raw.platform,
    platformUid: raw.platform_uid,
    name: raw.name,
    category: raw.category,
    isActive: raw.is_active,
    manualWeight: raw.manual_weight,
    fetchIntervalMin: raw.fetch_interval_min,
    notes: raw.notes,
    lastFetchAt: raw.last_fetch_at,
    createdAt: raw.created_at,
  };
}

type QualityStatsSnake = {
  total_contents: number;
  extracted_count: number;
  failed_count: number;
  pending_count: number;
  ignored_count: number;
  extraction_success_rate: number;
  active_creators: number;
  covered_creators: number;
  creator_coverage_rate: number;
  failure_explainability_rate: number;
  signal_mention_count: number;
  signal_event_count: number;
};

function mapQualityStats(raw: QualityStatsSnake): QualityStats {
  return {
    totalContents: raw.total_contents,
    extractedCount: raw.extracted_count,
    failedCount: raw.failed_count,
    pendingCount: raw.pending_count,
    ignoredCount: raw.ignored_count,
    extractionSuccessRate: raw.extraction_success_rate,
    activeCreators: raw.active_creators,
    coveredCreators: raw.covered_creators,
    creatorCoverageRate: raw.creator_coverage_rate,
    failureExplainabilityRate: raw.failure_explainability_rate,
    signalMentionCount: raw.signal_mention_count,
    signalEventCount: raw.signal_event_count,
  };
}

type FailureItemSnake = { stage: string | null; reason: string | null; count: number };

function mapFailureItem(raw: FailureItemSnake): FailureItem {
  return {
    stage: raw.stage,
    reason: raw.reason,
    count: raw.count,
  };
}

type CreatorStatsSnake = {
  creator_id: number;
  name: string;
  total: number;
  extracted: number;
  failed: number;
  success_rate: number;
  last_fetch_at: string | null;
};

function mapCreatorStats(raw: CreatorStatsSnake): CreatorStats {
  return {
    creatorId: raw.creator_id,
    name: raw.name,
    total: raw.total,
    extracted: raw.extracted,
    failed: raw.failed,
    successRate: raw.success_rate,
    lastFetchAt: raw.last_fetch_at,
  };
}

function isoOrNull(v: string | null | undefined): string | null {
  if (v == null || v === '') return null;
  return v;
}

type ContentItemSnake = {
  id: number;
  creator_name: string;
  platform_content_id: string;
  content_type: string;
  display_type: string;
  title: string | null;
  status: string;
  failure_stage: string | null;
  failure_reason: string | null;
  has_mentions: boolean;
  published_at: string | null;
  created_at: string | null;
};

function mapContentItem(raw: ContentItemSnake): ContentItem {
  return {
    id: raw.id,
    creatorName: raw.creator_name,
    platformContentId: raw.platform_content_id,
    contentType: raw.content_type,
    displayType: raw.display_type,
    title: raw.title,
    status: raw.status,
    failureStage: raw.failure_stage,
    failureReason: raw.failure_reason,
    hasMentions: raw.has_mentions,
    publishedAt: isoOrNull(raw.published_at as string | null),
    createdAt: isoOrNull(raw.created_at as string | null),
  };
}

type SignalEventSnake = {
  id: number;
  asset_name: string;
  asset_code: string | null;
  asset_type: string;
  market: string;
  event_type: string;
  event_date: string;
  score: number | null;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  creator_count: number;
  mention_count: number;
  top_creator_name: string | null;
  evidence: Record<string, unknown>[] | null;
  created_at: string | null;
};

function mapSignalEvent(raw: SignalEventSnake): SignalEvent {
  return {
    id: raw.id,
    assetName: raw.asset_name,
    assetCode: raw.asset_code,
    assetType: raw.asset_type,
    market: raw.market,
    eventType: raw.event_type,
    eventDate: typeof raw.event_date === 'string' ? raw.event_date : String(raw.event_date),
    score: raw.score,
    bullishCount: raw.bullish_count,
    bearishCount: raw.bearish_count,
    neutralCount: raw.neutral_count,
    creatorCount: raw.creator_count,
    mentionCount: raw.mention_count,
    topCreatorName: raw.top_creator_name,
    evidence: raw.evidence,
    createdAt: isoOrNull(raw.created_at as string | null),
  };
}

type MentionSnake = {
  id: number;
  content_id: number;
  creator_id: number;
  creator_name: string;
  asset_name: string;
  asset_code: string | null;
  asset_type: string;
  market: string;
  sentiment: string;
  confidence: number;
  is_primary: boolean;
  reasoning: string | null;
  trade_advice: string | null;
  key_levels: Record<string, unknown> | null;
  quality_flags: string[];
  source_url: string | null;
  published_at: string | null;
  created_at: string | null;
  content_text?: string | null;
  transcript_text?: string | null;
  summary_text?: string | null;
};

function mapMention(raw: MentionSnake): Mention {
  const levels = raw.key_levels;
  let keyLevels: Record<string, number[]> | null = null;
  if (levels && typeof levels === 'object') {
    keyLevels = {};
    for (const [k, v] of Object.entries(levels)) {
      if (Array.isArray(v)) {
        keyLevels[k] = v.map((x) => (typeof x === 'number' ? x : Number(x)));
      }
    }
    if (Object.keys(keyLevels).length === 0) keyLevels = null;
  }

  return {
    id: raw.id,
    contentId: raw.content_id,
    creatorId: raw.creator_id,
    creatorName: raw.creator_name,
    assetName: raw.asset_name,
    assetCode: raw.asset_code,
    assetType: raw.asset_type,
    market: raw.market,
    sentiment: raw.sentiment,
    confidence: raw.confidence,
    isPrimary: raw.is_primary,
    reasoning: raw.reasoning,
    tradeAdvice: raw.trade_advice,
    keyLevels,
    qualityFlags: raw.quality_flags ?? [],
    sourceUrl: raw.source_url,
    publishedAt: isoOrNull(raw.published_at as string | null),
    createdAt: isoOrNull(raw.created_at as string | null),
    ...(raw.content_text != null && raw.content_text !== ''
      ? { contentText: raw.content_text }
      : {}),
    ...(raw.transcript_text != null && raw.transcript_text !== ''
      ? { transcriptText: raw.transcript_text }
      : {}),
    ...(raw.summary_text != null && raw.summary_text !== ''
      ? { summaryText: raw.summary_text }
      : {}),
  };
}

type AssetDetailSnake = {
  asset_name: string;
  asset_code: string | null;
  asset_type: string;
  market: string;
  event: {
    event_type: string;
    score: number | null;
    event_date: string;
  } | null;
  sentiment_summary: { bullish: number; bearish: number; neutral: number };
  creator_count: number;
  mention_count: number;
  creators: { id: number; name: string; weight: number }[];
};

function mapAssetDetail(raw: AssetDetailSnake): AssetDetailOverview {
  return {
    assetName: raw.asset_name,
    assetCode: raw.asset_code,
    assetType: raw.asset_type,
    market: raw.market,
    event: raw.event
      ? {
          eventType: raw.event.event_type,
          score: raw.event.score,
          eventDate:
            typeof raw.event.event_date === 'string'
              ? raw.event.event_date
              : String(raw.event.event_date),
        }
      : null,
    sentimentSummary: raw.sentiment_summary,
    creatorCount: raw.creator_count,
    mentionCount: raw.mention_count,
    creators: raw.creators ?? [],
  };
}

function toCreatorCreatePayload(data: CreatorCreate): Record<string, unknown> {
  return {
    platform: data.platform ?? 'bilibili',
    platform_uid: data.platformUid,
    name: data.name,
    category: data.category ?? null,
    is_active: data.isActive ?? true,
    manual_weight: data.manualWeight ?? 1.0,
    fetch_interval_min: data.fetchIntervalMin ?? 60,
    notes: data.notes ?? null,
  };
}

function toCreatorUpdatePayload(data: CreatorUpdate): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (data.name !== undefined) out.name = data.name;
  if (data.category !== undefined) out.category = data.category;
  if (data.isActive !== undefined) out.is_active = data.isActive;
  if (data.manualWeight !== undefined) out.manual_weight = data.manualWeight;
  if (data.fetchIntervalMin !== undefined) out.fetch_interval_min = data.fetchIntervalMin;
  if (data.notes !== undefined) out.notes = data.notes;
  return out;
}

export function getSignalApiErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'parsedError' in err) {
    const pe = (err as { parsedError?: ParsedApiError }).parsedError;
    if (pe?.message) return pe.message;
  }
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === 'string') return d;
      if (Array.isArray(d)) {
        const first = d[0] as { msg?: string } | undefined;
        if (first?.msg) return first.msg;
      }
    }
  }
  if (err instanceof Error) return err.message;
  return '请求失败';
}

export const signalApi = {
  listCreators: (params?: { isActive?: boolean; category?: string }) =>
    apiClient
      .get<CreatorSnake[]>(`${BASE}/creators`, {
        params: {
          is_active: params?.isActive,
          category: params?.category,
        },
      })
      .then((r) => r.data.map(mapCreator)),

  createCreator: (data: CreatorCreate) =>
    apiClient
      .post<CreatorSnake>(`${BASE}/creators`, toCreatorCreatePayload(data))
      .then((r) => mapCreator(r.data)),

  getCreator: (id: number) =>
    apiClient.get<CreatorSnake>(`${BASE}/creators/${id}`).then((r) => mapCreator(r.data)),

  updateCreator: (id: number, data: CreatorUpdate) =>
    apiClient
      .put<CreatorSnake>(`${BASE}/creators/${id}`, toCreatorUpdatePayload(data))
      .then((r) => mapCreator(r.data)),

  getQualityStats: (days?: number) =>
    apiClient
      .get<QualityStatsSnake>(`${BASE}/quality/stats`, { params: { days } })
      .then((r) => mapQualityStats(r.data)),

  getFunnel: (days?: number) =>
    apiClient.get<{ funnel: Record<string, number> }>(`${BASE}/quality/funnel`, { params: { days } }).then(
      (r): FunnelData => ({ funnel: r.data.funnel })
    ),

  getFailures: (days?: number) =>
    apiClient
      .get<FailureItemSnake[]>(`${BASE}/quality/failures`, { params: { days } })
      .then((r) => r.data.map(mapFailureItem)),

  getCreatorStats: (days?: number) =>
    apiClient
      .get<CreatorStatsSnake[]>(`${BASE}/quality/creators`, { params: { days } })
      .then((r) => r.data.map(mapCreatorStats)),

  listContents: (
    params?: {
      status?: string;
      displayType?: string;
      creatorId?: number;
      limit?: number;
      offset?: number;
    }
  ) =>
    apiClient
      .get<ContentItemSnake[]>(`${BASE}/contents`, {
        params: {
          status: params?.status,
          display_type: params?.displayType,
          creator_id: params?.creatorId,
          limit: params?.limit,
          offset: params?.offset,
        },
      })
      .then((r) => r.data.map(mapContentItem)),

  getContent: (id: number) => apiClient.get(`${BASE}/contents/${id}`).then((r) => r.data),

  retryContent: (id: number) => apiClient.post(`${BASE}/contents/${id}/retry`).then((r) => r.data),

  ignoreContent: (id: number) => apiClient.post(`${BASE}/contents/${id}/ignore`).then((r) => r.data),

  listEvents: (params?: EventListParams) =>
    apiClient
      .get<SignalEventSnake[]>(`${BASE}/events`, {
        params: {
          event_type: params?.eventType,
          market: params?.market,
          asset_type: params?.assetType,
          date_from: params?.dateFrom,
          date_to: params?.dateTo,
          sort_by: params?.sortBy,
          sort_order: params?.sortOrder,
          limit: params?.limit,
          offset: params?.offset,
        },
      })
      .then((r) => r.data.map(mapSignalEvent)),

  getEvent: (id: number) =>
    apiClient.get<SignalEventSnake>(`${BASE}/events/${id}`).then((r) => mapSignalEvent(r.data)),

  getOverviewStats: (days?: number) =>
    apiClient
      .get<QualityStatsSnake>(`${BASE}/stats`, { params: { days } })
      .then((r) => mapQualityStats(r.data)),

  getAsset: (identifier: string) =>
    apiClient
      .get<AssetDetailSnake>(`${BASE}/assets/${encodeURIComponent(identifier)}`)
      .then((r) => mapAssetDetail(r.data)),

  getAssetMentions: (identifier: string, params?: MentionListParams) =>
    apiClient
      .get<MentionSnake[]>(`${BASE}/assets/${encodeURIComponent(identifier)}/mentions`, {
        params: {
          sentiment: params?.sentiment,
          creator_id: params?.creatorId,
          include_content: params?.includeContent,
          limit: params?.limit,
          offset: params?.offset,
        },
      })
      .then((r) => r.data.map(mapMention)),

  getAssetTimeline: (identifier: string) =>
    apiClient.get(`${BASE}/assets/${encodeURIComponent(identifier)}/timeline`).then((r) => r.data),

  triggerPipeline: (maxPages?: number, processLimit?: number) =>
    apiClient
      .post(`${BASE}/pipeline/run`, null, {
        params: {
          ...(maxPages ? { max_pages: maxPages } : {}),
          ...(processLimit !== undefined ? { process_limit: processLimit } : {}),
        },
      })
      .then((r) => r.data),

  cancelPipeline: () =>
    apiClient.post(`${BASE}/pipeline/cancel`).then((r) => r.data),

  getPipelineStatus: () =>
    apiClient.get<PipelineStatus>(`${BASE}/pipeline/status`).then((r) => r.data),

  getPipelineProgress: () =>
    apiClient
      .get<Record<string, unknown>>(`${BASE}/pipeline/progress`)
      .then((r) => {
        const d = r.data;
        return {
          executing: Boolean(d.executing),
          startedAt: d.started_at as string | undefined,
          finishedAt: d.finished_at as string | undefined,
          currentStep: (d.current_step as string) || '',
          stepIndex: d.step_index as number | undefined,
          totalSteps: d.total_steps as number | undefined,
          processed: (d.processed as number) || 0,
          total: (d.total as number) || 0,
          failed: d.failed as number | undefined,
          message: (d.message as string) || '',
          elapsedMs: d.elapsed_ms as number | undefined,
        } as PipelineProgress;
      }),

  getPipelineLogs: (limit?: number) =>
    apiClient.get(`${BASE}/pipeline/logs`, { params: { limit } }).then((r) => r.data),
};
