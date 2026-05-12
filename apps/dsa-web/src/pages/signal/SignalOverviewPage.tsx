import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { QualityStats, SignalEvent } from '../../types/signal';
import { Card, StatCard } from '../../components/common';
import { cn } from '../../utils/cn';

type EventTab = 'all' | 'opportunity' | 'risk' | 'conflict' | 'watch';

const TAB_CONFIG: { key: EventTab; label: string; apiType?: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'opportunity', label: '机会', apiType: 'opportunity' },
  { key: 'risk', label: '风险', apiType: 'risk' },
  { key: 'conflict', label: '分歧', apiType: 'conflict' },
  { key: 'watch', label: '观察', apiType: 'watch' },
];

const SELECT_CLASS =
  'input-surface input-focus-glow h-10 rounded-xl border border-border/60 bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';

const MARKET_OPTIONS = [
  { value: '', label: '全部市场' },
  { value: 'cn', label: 'A 股 (cn)' },
  { value: 'hk', label: '港股 (hk)' },
  { value: 'us', label: '美股 (us)' },
  { value: 'unknown', label: '未知' },
];

const ASSET_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'stock', label: '股票' },
  { value: 'index', label: '指数' },
  { value: 'etf', label: 'ETF' },
];

const PAGE_SIZE = 30;

function formatPct(rate: number): string {
  if (!Number.isFinite(rate)) return '—';
  return `${(rate * 100).toFixed(1)}%`;
}

function formatUpdated(e: SignalEvent): string {
  const raw = e.createdAt ?? e.eventDate;
  if (!raw) return '—';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function eventTypeStyle(t: string): { label: string; className: string } {
  switch (t) {
    case 'opportunity':
      return { label: '机会', className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/25' };
    case 'risk':
      return { label: '风险', className: 'bg-red-500/15 text-red-600 dark:text-red-400 ring-1 ring-red-500/25' };
    case 'conflict':
      return { label: '分歧', className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/30' };
    case 'watch':
      return { label: '观察', className: 'bg-slate-500/15 text-slate-600 dark:text-slate-300 ring-1 ring-slate-400/25' };
    default:
      return { label: t, className: 'bg-zinc-500/10 text-secondary-text ring-1 ring-border/60' };
  }
}

function directionOf(e: SignalEvent): { key: string; label: string; className: string } {
  if (e.eventType === 'conflict') {
    return { key: 'conflict', label: '分歧', className: 'text-amber-600 dark:text-amber-400' };
  }
  if (e.bullishCount > e.bearishCount) {
    return { key: 'bullish', label: '看多', className: 'text-emerald-600 dark:text-emerald-400' };
  }
  if (e.bearishCount > e.bullishCount) {
    return { key: 'bearish', label: '看空', className: 'text-red-600 dark:text-red-400' };
  }
  return { key: 'neutral', label: '中性', className: 'text-secondary-text' };
}

function assetIdentifier(e: SignalEvent): string {
  return e.assetCode || e.assetName;
}

const SignalOverviewPage = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<EventTab>('all');
  const [market, setMarket] = useState('');
  const [assetType, setAssetType] = useState('');
  const [stats, setStats] = useState<QualityStats | null>(null);
  const [events, setEvents] = useState<SignalEvent[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const tabApiType = TAB_CONFIG.find((t) => t.key === tab)?.apiType;

  const loadStats = useCallback(async () => {
    try {
      setLoadingStats(true);
      const s = await signalApi.getOverviewStats(1);
      setStats(s);
    } catch (err) {
      console.error(err);
      setStats(null);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      setError(null);
      setLoadingEvents(true);
      const offset = (page - 1) * PAGE_SIZE;
      const list = await signalApi.listEvents({
        eventType: tabApiType,
        market: market || undefined,
        assetType: assetType || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setEvents(list);
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
      setEvents([]);
    } finally {
      setLoadingEvents(false);
    }
  }, [tabApiType, market, assetType, page]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    setPage(1);
  }, [tab, market, assetType]);

  const hasNext = events.length >= PAGE_SIZE;
  const hasPrev = page > 1;

  const onOpenAsset = (e: SignalEvent) => {
    const id = assetIdentifier(e);
    navigate(`/signals/asset/${encodeURIComponent(id)}`);
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">信号总览</h1>
        <p className="mt-1 text-sm text-secondary-text">今日处理指标与聚合事件</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="今日内容数"
          value={loadingStats ? '…' : (stats?.totalContents ?? '—')}
          tone="primary"
        />
        <StatCard
          label="提取成功率"
          value={loadingStats ? '…' : formatPct(stats?.extractionSuccessRate ?? NaN)}
          tone="success"
        />
        <StatCard
          label="UP主覆盖率"
          value={loadingStats ? '…' : formatPct(stats?.creatorCoverageRate ?? NaN)}
          tone="warning"
        />
        <StatCard
          label="失败可解释率"
          value={loadingStats ? '…' : formatPct(stats?.failureExplainabilityRate ?? NaN)}
          tone="default"
        />
      </div>

      <Card className="p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
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
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-secondary-text">
              市场
              <select className={cn(SELECT_CLASS, 'min-w-[9.5rem]')} value={market} onChange={(e) => setMarket(e.target.value)}>
                {MARKET_OPTIONS.map((o) => (
                  <option key={o.value || 'm-all'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-secondary-text">
              标的类型
              <select
                className={cn(SELECT_CLASS, 'min-w-[9rem]')}
                value={assetType}
                onChange={(e) => setAssetType(e.target.value)}
              >
                {ASSET_TYPE_OPTIONS.map((o) => (
                  <option key={o.value || 'a-all'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        {loadingEvents ? (
          <Card className="p-10 text-center text-secondary-text">加载事件…</Card>
        ) : events.length === 0 ? (
          <Card className="p-10 text-center text-secondary-text">暂无事件</Card>
        ) : (
          events.map((e) => {
            const et = eventTypeStyle(e.eventType);
            const dir = directionOf(e);
            return (
              <button
                key={e.id}
                type="button"
                onClick={() => onOpenAsset(e)}
                className="block w-full rounded-2xl border border-border/70 bg-card/80 p-4 text-left shadow-soft-card transition-all hover:border-cyan/25 hover:bg-card"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-lg font-semibold text-foreground">{e.assetName}</span>
                      {e.assetCode && (
                        <span className="rounded-md bg-muted/60 px-2 py-0.5 text-xs text-secondary-text">{e.assetCode}</span>
                      )}
                      <span
                        className={cn(
                          'inline-flex rounded-lg px-2 py-0.5 text-xs font-medium',
                          et.className
                        )}
                      >
                        {et.label}
                      </span>
                      <span className={cn('text-sm font-medium', dir.className)}>{dir.label}</span>
                    </div>
                    <p className="mt-1 text-xs text-secondary-text">
                      {e.market} · {e.assetType} · 更新 {formatUpdated(e)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3 text-sm sm:flex-col sm:items-end sm:text-right">
                    <div>
                      <span className="text-secondary-text">得分 </span>
                      <span className="font-semibold text-foreground">
                        {e.score != null ? e.score.toFixed(1) : '—'}
                      </span>
                    </div>
                    <div className="text-secondary-text">
                      {e.creatorCount} 位 UP · {e.mentionCount} 条提及
                    </div>
                    {e.topCreatorName && (
                      <div className="text-xs text-secondary-text">主力观点：{e.topCreatorName}</div>
                    )}
                  </div>
                </div>
              </button>
            );
          })
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
    </div>
  );
};

export default SignalOverviewPage;
