import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Settings } from 'lucide-react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { SignalEvent } from '../../types/signal';
import { Card } from '../../components/common';
import { cn } from '../../utils/cn';
import EventCard from '../../components/signal/EventCard';
import StatusBar from '../../components/signal/StatusBar';
import ResearchSidebar from '../../components/signal/ResearchSidebar';

type EventTab = 'all' | 'opportunity' | 'risk' | 'conflict' | 'watch';

const TAB_CONFIG: { key: EventTab; label: string; apiType?: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'opportunity', label: '机会', apiType: 'opportunity' },
  { key: 'risk', label: '风险', apiType: 'risk' },
  { key: 'conflict', label: '分歧', apiType: 'conflict' },
  { key: 'watch', label: '观察', apiType: 'watch' },
];

const PAGE_SIZE = 30;

function assetIdentifier(e: SignalEvent): string {
  return e.assetCode || e.assetName;
}

const SignalBriefingPage = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<EventTab>('all');
  const [events, setEvents] = useState<SignalEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<SignalEvent | null>(null);
  const [triggering, setTriggering] = useState(false);

  const tabApiType = TAB_CONFIG.find((t) => t.key === tab)?.apiType;
  const showTypeLabel = tab === 'all';

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
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    setPage(1);
  }, [tab]);

  const hasNext = events.length >= PAGE_SIZE;
  const hasPrev = page > 1;

  const sidebarOpen = selected != null;
  const sidebarId = selected ? assetIdentifier(selected) : null;

  const selectedId = useMemo(() => (selected ? selected.id : null), [selected]);

  const onPick = (e: SignalEvent) => {
    setSelected((prev) => (prev?.id === e.id ? null : e));
  };

  const handleTrigger = useCallback(async () => {
    try {
      setTriggering(true);
      await signalApi.triggerPipeline();
    } catch (err) {
      console.error('Failed to trigger pipeline:', err);
    } finally {
      setTriggering(false);
    }
  }, []);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">信号简报</h1>
        <p className="mt-1 text-sm text-secondary-text">今日聚合事件与研判侧栏</p>
      </div>

      <StatusBar />

      {error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          {TAB_CONFIG.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'rounded-xl border px-3 py-2 text-sm font-medium transition-colors',
                tab === t.key
                  ? 'border-cyan/40 bg-cyan/15 text-cyan shadow-sm'
                  : 'border-border/60 text-secondary-text hover:bg-hover'
              )}
            >
              {t.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              disabled={triggering}
              onClick={handleTrigger}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border border-border/60 px-3 py-2 text-sm font-medium',
                'text-secondary-text hover:bg-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'
              )}
              aria-label="运行采集"
            >
              <Play className={cn('h-4 w-4', triggering && 'animate-pulse')} />
              {triggering ? '运行中…' : '运行采集'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/signals/settings')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border border-border/60 px-3 py-2 text-sm font-medium',
                'text-secondary-text hover:bg-hover hover:text-foreground'
              )}
              aria-label="信号设置"
            >
              <Settings className="h-4 w-4" />
              设置
            </button>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        {loadingEvents ? (
          <Card className="p-10 text-center text-secondary-text">加载事件…</Card>
        ) : events.length === 0 ? (
          <Card className="p-10 text-center text-secondary-text">暂无事件</Card>
        ) : (
          events.map((e) => (
            <EventCard
              key={e.id}
              event={e}
              showTypeLabel={showTypeLabel}
              isSelected={selectedId === e.id}
              onClick={() => onPick(e)}
            />
          ))
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-secondary-text">
          每页 {PAGE_SIZE} 条 · 第 {page} 页
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!hasPrev || loadingEvents}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            上一页
          </button>
          <button
            type="button"
            disabled={!hasNext || loadingEvents}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      </div>

      <ResearchSidebar
        open={sidebarOpen}
        event={selected}
        identifier={sidebarId}
        onClose={() => setSelected(null)}
      />
    </div>
  );
};

export default SignalBriefingPage;
