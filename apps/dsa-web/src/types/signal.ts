export interface Creator {
  id: number;
  platform: string;
  platformUid: string;
  name: string;
  category: string | null;
  isActive: boolean;
  manualWeight: number;
  fetchIntervalMin: number;
  notes: string | null;
  lastFetchAt: string | null;
  createdAt: string | null;
}

export interface CreatorCreate {
  platform?: string;
  platformUid: string;
  name: string;
  category?: string;
  isActive?: boolean;
  manualWeight?: number;
  fetchIntervalMin?: number;
  notes?: string;
}

export interface CreatorUpdate {
  name?: string;
  category?: string;
  isActive?: boolean;
  manualWeight?: number;
  fetchIntervalMin?: number;
  /** Use `null` to clear optional text fields. */
  notes?: string | null;
}

export interface QualityStats {
  totalContents: number;
  extractedCount: number;
  failedCount: number;
  pendingCount: number;
  ignoredCount: number;
  extractionSuccessRate: number;
  activeCreators: number;
  coveredCreators: number;
  creatorCoverageRate: number;
  failureExplainabilityRate: number;
}

export interface FunnelData {
  funnel: Record<string, number>;
}

export interface FailureItem {
  stage: string | null;
  reason: string | null;
  count: number;
}

export interface CreatorStats {
  creatorId: number;
  name: string;
  total: number;
  extracted: number;
  failed: number;
  successRate: number;
  lastFetchAt: string | null;
}

export interface ContentItem {
  id: number;
  creatorName: string;
  platformContentId: string;
  contentType: string;
  displayType: string;
  title: string | null;
  status: string;
  failureStage: string | null;
  failureReason: string | null;
  hasMentions: boolean;
  publishedAt: string | null;
  createdAt: string | null;
}

export interface Mention {
  id: number;
  contentId: number;
  creatorId: number;
  creatorName: string;
  assetName: string;
  assetCode: string | null;
  assetType: string;
  market: string;
  sentiment: string;
  confidence: number;
  isPrimary: boolean;
  reasoning: string | null;
  tradeAdvice: string | null;
  keyLevels: Record<string, number[]> | null;
  qualityFlags: string[];
  sourceUrl: string | null;
  publishedAt: string | null;
  createdAt: string | null;
  contentText?: string;
  transcriptText?: string;
  summaryText?: string;
}

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

export interface MentionListParams {
  sentiment?: string;
  creatorId?: number;
  includeContent?: boolean;
  limit?: number;
  offset?: number;
}

export interface SignalEvent {
  id: number;
  assetName: string;
  assetCode: string | null;
  assetType: string;
  market: string;
  eventType: string;
  eventDate: string;
  score: number | null;
  bullishCount: number;
  bearishCount: number;
  neutralCount: number;
  creatorCount: number;
  mentionCount: number;
  topCreatorName: string | null;
  evidence: Record<string, unknown>[] | null;
  createdAt: string | null;
}

/** GET /signals/assets/{identifier} — overview for a single asset. */
export interface AssetDetailOverview {
  assetName: string;
  assetCode: string | null;
  assetType: string;
  market: string;
  event: {
    eventType: string;
    score: number | null;
    eventDate: string;
  } | null;
  sentimentSummary: {
    bullish: number;
    bearish: number;
    neutral: number;
  };
  creatorCount: number;
  mentionCount: number;
  creators: { id: number; name: string; weight: number }[];
}

export interface PipelineStatus {
  running: boolean;
  lastResult: Record<string, unknown> | null;
  jobId: string;
}
