import apiClient from './index';
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

export const signalApi = {
  // Creators
  listCreators: (params?: { isActive?: boolean; category?: string }) =>
    apiClient.get<Creator[]>(`${BASE}/creators`, { params }).then((r) => r.data),

  createCreator: (data: CreatorCreate) =>
    apiClient.post<Creator>(`${BASE}/creators`, data).then((r) => r.data),

  getCreator: (id: number) =>
    apiClient.get<Creator>(`${BASE}/creators/${id}`).then((r) => r.data),

  updateCreator: (id: number, data: CreatorUpdate) =>
    apiClient.put<Creator>(`${BASE}/creators/${id}`, data).then((r) => r.data),

  // Quality
  getQualityStats: (days?: number) =>
    apiClient.get<QualityStats>(`${BASE}/quality/stats`, { params: { days } }).then((r) => r.data),

  getFunnel: (days?: number) =>
    apiClient.get<FunnelData>(`${BASE}/quality/funnel`, { params: { days } }).then((r) => r.data),

  getFailures: (days?: number) =>
    apiClient.get<FailureItem[]>(`${BASE}/quality/failures`, { params: { days } }).then((r) => r.data),

  getCreatorStats: (days?: number) =>
    apiClient.get<CreatorStats[]>(`${BASE}/quality/creators`, { params: { days } }).then((r) => r.data),

  // Content
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

  // Events / Overview
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
    apiClient.get<QualityStats>(`${BASE}/stats`, { params: { days } }).then((r) => r.data),

  // Asset
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

  // Pipeline
  triggerPipeline: () => apiClient.post(`${BASE}/pipeline/run`).then((r) => r.data),

  getPipelineStatus: () =>
    apiClient.get<PipelineStatus>(`${BASE}/pipeline/status`).then((r) => r.data),

  getPipelineLogs: (limit?: number) =>
    apiClient.get(`${BASE}/pipeline/logs`, { params: { limit } }).then((r) => r.data),
};
