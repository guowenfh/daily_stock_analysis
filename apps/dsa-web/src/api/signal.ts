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
  PipelineStatus,
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
  ) => apiClient.get<ContentItem[]>(`${BASE}/contents`, { params }).then((r) => r.data),

  getContent: (id: number) => apiClient.get(`${BASE}/contents/${id}`).then((r) => r.data),

  retryContent: (id: number) => apiClient.post(`${BASE}/contents/${id}/retry`).then((r) => r.data),

  ignoreContent: (id: number) => apiClient.post(`${BASE}/contents/${id}/ignore`).then((r) => r.data),

  listEvents: (
    params?: {
      eventType?: string;
      market?: string;
      assetType?: string;
      dateFrom?: string;
      dateTo?: string;
      limit?: number;
      offset?: number;
    }
  ) => apiClient.get<SignalEvent[]>(`${BASE}/events`, { params }).then((r) => r.data),

  getEvent: (id: number) => apiClient.get<SignalEvent>(`${BASE}/events/${id}`).then((r) => r.data),

  getOverviewStats: (days?: number) =>
    apiClient
      .get<QualityStatsSnake>(`${BASE}/stats`, { params: { days } })
      .then((r) => mapQualityStats(r.data)),

  getAsset: (identifier: string) =>
    apiClient.get(`${BASE}/assets/${encodeURIComponent(identifier)}`).then((r) => r.data),

  getAssetMentions: (
    identifier: string,
    params?: { sentiment?: string; creatorId?: number; limit?: number; offset?: number }
  ) =>
    apiClient
      .get<Mention[]>(`${BASE}/assets/${encodeURIComponent(identifier)}/mentions`, { params })
      .then((r) => r.data),

  getAssetTimeline: (identifier: string) =>
    apiClient.get(`${BASE}/assets/${encodeURIComponent(identifier)}/timeline`).then((r) => r.data),

  triggerPipeline: () => apiClient.post(`${BASE}/pipeline/run`).then((r) => r.data),

  getPipelineStatus: () =>
    apiClient.get<PipelineStatus>(`${BASE}/pipeline/status`).then((r) => r.data),

  getPipelineLogs: (limit?: number) =>
    apiClient.get(`${BASE}/pipeline/logs`, { params: { limit } }).then((r) => r.data),
};
