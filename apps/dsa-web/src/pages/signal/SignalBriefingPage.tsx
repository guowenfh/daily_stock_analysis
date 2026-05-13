import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Play, Square, Zap } from 'lucide-react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { SignalEvent, PipelineProgress } from '../../types/signal';
import { Card } from '../../components/common';
import { cn } from '../../utils/cn';
import EventCard from '../../components/signal/EventCard';
import StatusBar from '../../components/signal/StatusBar';
import ResearchSidebar from '../../components/signal/ResearchSidebar';
import CreatorManagePage from './CreatorManagePage';
import QualityDashboard from './QualityDashboard';
import ContentQueuePage from './ContentQueuePage';

type TopTab = 'briefing' | 'creators' | 'quality' | 'content';
type EventTab = 'all' | 'opportunity' | 'risk' | 'conflict' | 'watch';

const TOP_TABS: { key: TopTab; label: string }[] = [
  { key: 'briefing', label: '简报' },
  { key: 'creators', label: 'UP主管理' },
  { key: 'quality', label: '采集质量' },
  { key: 'content', label: '内容队列' },
];

const EVENT_TABS: { key: EventTab; label: string; apiType?: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'opportunity', label: '机会', apiType: 'opportunity' },
  { key: 'risk', label: '风险', apiType: 'risk' },
  { key: 'conflict', label: '分歧', apiType: 'conflict' },
  { key: 'watch', label: '观察', apiType: 'watch' },
];

const PAGE_SIZE = 30;

const STEP_LABELS: Record<string, string> = {
  init: '初始化',
  collect: '采集',
  enrich: '富化',
  extract: 'LLM 提取',
  build_events: '构建事件',
  compute_stats: '统计',
  done: '完成',
};

function assetIdentifier(e: SignalEvent): string {
  return e.assetCode || e.assetName;
}

function formatElapsed(ms?: number): string {
  if (!ms) return '';
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const min = Math.floor(ms / 60_000);
  const sec = Math.round((ms % 60_000) / 1000);
  return `${min}m${sec}s`;
}

function PipelineProgressBar({ progress }: { progress: PipelineProgress }) {
  const pct = progress.total > 0 ? Math.round((progress.processed / progress.total) * 100) : 0;
  const stepLabel = STEP_LABELS[progress.currentStep] || progress.currentStep;

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card/60 p-3">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">
          管线运行中 · {stepLabel}
        </span>
        <span className="text-secondary-text">
          {progress.processed}/{progress.total}
          {progress.elapsedMs ? ` · ${formatElapsed(progress.elapsedMs)}` : ''}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-border/40">
        <div
          className="h-full rounded-full bg-cyan transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-secondary-text">{progress.message}</p>
    </div>
  );
}

function parseTopTab(raw: string | null): TopTab {
  if (raw === 'creators' || raw === 'quality' || raw === 'content' || raw === 'briefing') return raw;
  return 'briefing';
}

const SignalBriefingPage = () => {
  const [search, setSearch] = useSearchParams();
  const topTab = useMemo(() => parseTopTab(search.get('tab')), [search]);

  const [eventTab, setEventTab] = useState<EventTab>('all');
  const [events, setEvents] = useState<SignalEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<SignalEvent | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const setTopTab = useCallback(
    (next: TopTab) => {
      const p = new URLSearchParams(search);
      if (next === 'briefing') {
        p.delete('tab');
      } else {
        p.set('tab', next);
      }
      setSearch(p, { replace: false });
    },
    [search, setSearch]
  );

  const tabApiType = EVENT_TABS.find((t) => t.key === eventTab)?.apiType;
  const showTypeLabel = eventTab === 'all';

  const loadEvents = useCallback(async () => {
    try {
      setError(null);
      setLoadingEvents(true);
      const offset = (page - 1) * PAGE_SIZE;
      const list = await signalApi.listEvents({
        eventType: tabApiType,
        limit: PAGE_SIZE,
        offset,
        sortBy: 'score',
        sortOrder: 'desc',
      });
      const sorted = [...list].sort((a, b) => {
        const sa = a.score ?? Number.NEGATIVE_INFINITY;
        const sb = b.score ?? Number.NEGATIVE_INFINITY;
        return sb - sa;
      });
      setEvents(sorted);
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
      setEvents([]);
    } finally {
      setLoadingEvents(false);
    }
  }, [tabApiType, page]);

  useEffect(() => {
    if (topTab === 'briefing') void loadEvents();
  }, [loadEvents, topTab]);

  useEffect(() => {
    setPage(1);
  }, [eventTab]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchProgress = useCallback(async () => {
    try {
      const p = await signalApi.getPipelineProgress();
      setProgress(p);
      if (!p.executing) {
        stopPolling();
        setTriggering(false);
        void loadEvents();
      }
    } catch {
      // ignore
    }
  }, [loadEvents, stopPolling]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    void fetchProgress();
    pollRef.current = setInterval(fetchProgress, 20000);
  }, [fetchProgress]);

  useEffect(() => {
    signalApi.getPipelineProgress().then((p) => {
      setProgress(p);
      if (p.executing) {
        setTriggering(true);
        startPolling();
      }
    }).catch(() => {});
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const hasNext = events.length >= PAGE_SIZE;
  const hasPrev = page > 1;
  const sidebarOpen = selected != null;
  const sidebarId = selected ? assetIdentifier(selected) : null;
  const selectedId = useMemo(() => (selected ? selected.id : null), [selected]);

  const onPick = (e: SignalEvent) => {
    setSelected((prev) => (prev?.id === e.id ? null : e));
  };

  const handleTrigger = useCallback(async (maxPages: number = 3, processLimit: number = 0) => {
    try {
      setTriggering(true);
      const res = await signalApi.triggerPipeline(maxPages, processLimit);
      if (res.status === 'already_running') {
        startPolling();
        return;
      }
      startPolling();
    } catch (err) {
      console.error('Failed to trigger pipeline:', err);
      setTriggering(false);
    }
  }, [startPolling]);

  const handleCancel = useCallback(async () => {
    try {
      await signalApi.cancelPipeline();
    } catch (err) {
      console.error('Failed to cancel pipeline:', err);
    }
  }, []);

  const isRunning = triggering || (progress?.executing ?? false);

  return (
    <div className="space-y-5 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">信号中心</h1>
          <p className="mt-0.5 text-sm text-secondary-text">采集 · 提取 · 研判</p>
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <button
              type="button"
              onClick={handleCancel}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border border-red-500/40 px-3 py-1.5 text-sm font-medium',
                'text-red-600 hover:bg-red-500/10 dark:text-red-400'
              )}
            >
              <Square className="h-3.5 w-3.5" />
              停止
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() => handleTrigger(3, 20)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-border/60 px-3 py-1.5 text-sm font-medium text-secondary-text hover:bg-hover hover:text-foreground"
              >
                <Play className="h-3.5 w-3.5" />
                采集
              </button>
              <button
                type="button"
                onClick={() => handleTrigger(3, 0)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-cyan/40 px-3 py-1.5 text-sm font-medium text-cyan hover:bg-cyan/10"
              >
                <Zap className="h-3.5 w-3.5" />
                全量提取
              </button>
            </>
          )}
        </div>
      </div>

      {/* Pipeline progress */}
      {isRunning ? (
        progress?.executing ? (
          <PipelineProgressBar progress={progress} />
        ) : (
          <div className="rounded-xl border border-border/60 bg-card/60 p-3 text-sm text-secondary-text">
            管线启动中…
          </div>
        )
      ) : null}

      {/* Top-level tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border/40 pb-3">
        {TOP_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTopTab(t.key)}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition-colors',
              topTab === t.key
                ? 'border-cyan/40 bg-cyan/15 text-cyan shadow-sm'
                : 'border-border/60 text-secondary-text hover:bg-hover'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {topTab === 'briefing' ? (
        <BriefingContent
          eventTab={eventTab}
          setEventTab={setEventTab}
          events={events}
          loadingEvents={loadingEvents}
          error={error}
          showTypeLabel={showTypeLabel}
          selectedId={selectedId}
          onPick={onPick}
          page={page}
          setPage={setPage}
          hasPrev={hasPrev}
          hasNext={hasNext}
        />
      ) : null}
      {topTab === 'creators' ? <CreatorManagePage /> : null}
      {topTab === 'quality' ? <QualityDashboard /> : null}
      {topTab === 'content' ? <ContentQueuePage /> : null}

      {/* Research sidebar */}
      <ResearchSidebar
        open={sidebarOpen}
        event={selected}
        identifier={sidebarId}
        onClose={() => setSelected(null)}
      />
    </div>
  );
};

type BriefingContentProps = {
  eventTab: EventTab;
  setEventTab: (t: EventTab) => void;
  events: SignalEvent[];
  loadingEvents: boolean;
  error: string | null;
  showTypeLabel: boolean;
  selectedId: number | null;
  onPick: (e: SignalEvent) => void;
  page: number;
  setPage: (fn: (p: number) => number) => void;
  hasPrev: boolean;
  hasNext: boolean;
};

function BriefingContent({
  eventTab,
  setEventTab,
  events,
  loadingEvents,
  error,
  showTypeLabel,
  selectedId,
  onPick,
  page,
  setPage,
  hasPrev,
  hasNext,
}: BriefingContentProps) {
  return (
    <div className="space-y-4">
      <StatusBar />

      {error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      ) : null}

      {/* Event sub-tabs */}
      <div className="flex flex-wrap items-center gap-2">
        {EVENT_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setEventTab(t.key)}
            className={cn(
              'rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors',
              eventTab === t.key
                ? 'border-cyan/40 bg-cyan/10 text-cyan'
                : 'border-border/50 text-secondary-text hover:bg-hover'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Event grid */}
      {loadingEvents ? (
        <Card className="p-10 text-center text-secondary-text">加载事件…</Card>
      ) : events.length === 0 ? (
        <Card className="p-10 text-center text-secondary-text">暂无事件</Card>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {events.map((e) => (
            <EventCard
              key={e.id}
              event={e}
              showTypeLabel={showTypeLabel}
              isSelected={selectedId === e.id}
              onClick={() => onPick(e)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-secondary-text">
          每页 {PAGE_SIZE} 条 · 第 {page} 页
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!hasPrev || loadingEvents}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-xl border border-border/60 px-3 py-1.5 text-sm font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            上一页
          </button>
          <button
            type="button"
            disabled={!hasNext || loadingEvents}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-xl border border-border/60 px-3 py-1.5 text-sm font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}

export default SignalBriefingPage;
