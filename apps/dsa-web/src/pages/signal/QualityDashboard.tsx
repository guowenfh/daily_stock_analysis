import { useCallback, useEffect, useState } from 'react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { QualityStats, FunnelData, FailureItem, CreatorStats } from '../../types/signal';
import { Card, StatCard } from '../../components/common';
import { cn } from '../../utils/cn';

type RangeDays = 1 | 7 | 30;

const RANGE_OPTIONS: { value: RangeDays; label: string }[] = [
  { value: 1, label: '1 天' },
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
];

const FUNNEL_SEGMENTS: { key: string; label: string; className: string }[] = [
  { key: 'collected', label: '已采集', className: 'bg-slate-400/90' },
  { key: 'pending_enrich', label: '待丰富', className: 'bg-amber-400/90' },
  { key: 'pending_extract', label: '待提取', className: 'bg-orange-400/90' },
  { key: 'extracted', label: '已提取', className: 'bg-emerald-500/90' },
  { key: 'failed', label: '失败', className: 'bg-red-500/90' },
];

const EXTRA_FUNNEL_KEYS: { key: string; label: string; className: string }[] = [
  { key: 'low_confidence', label: '低置信', className: 'bg-teal-500/85' },
  { key: 'ignored', label: '已忽略', className: 'bg-zinc-400/80' },
];

function formatPct(ratio: number): string {
  if (!Number.isFinite(ratio)) return '—';
  return `${(ratio * 100).toFixed(1)}%`;
}

function formatLastFetch(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function buildFunnelSegments(funnel: Record<string, number>) {
  const primary = FUNNEL_SEGMENTS.map((s) => ({
    ...s,
    count: funnel[s.key] ?? 0,
  }));
  const extras = EXTRA_FUNNEL_KEYS.filter((s) => (funnel[s.key] ?? 0) > 0).map((s) => ({
    ...s,
    count: funnel[s.key] ?? 0,
  }));
  return [...primary, ...extras];
}

const QualityDashboard = () => {
  const [days, setDays] = useState<RangeDays>(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<QualityStats | null>(null);
  const [funnel, setFunnel] = useState<FunnelData | null>(null);
  const [creatorRows, setCreatorRows] = useState<CreatorStats[]>([]);
  const [failures, setFailures] = useState<FailureItem[]>([]);

  const load = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      const [s, f, c, fl] = await Promise.all([
        signalApi.getQualityStats(days),
        signalApi.getFunnel(days),
        signalApi.getCreatorStats(days),
        signalApi.getFailures(days),
      ]);
      setStats(s);
      setFunnel(f);
      setCreatorRows(c);
      setFailures(fl);
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const segments = funnel ? buildFunnelSegments(funnel.funnel) : [];
  const funnelTotal = segments.reduce((a, s) => a + s.count, 0);

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">采集质量</h1>
          <p className="mt-1 text-sm text-secondary-text">内容处理漏斗、UP主表现与失败原因分布</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-secondary-text">时间范围</span>
          <div className="flex rounded-xl border border-border bg-card/60 p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setDays(opt.value)}
                className={cn(
                  'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  days === opt.value
                    ? 'bg-cyan text-primary-foreground shadow-sm'
                    : 'text-secondary-text hover:bg-muted/80'
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <div
          className="rounded-xl border border-danger/40 bg-danger/8 px-4 py-3 text-sm text-[hsl(var(--color-danger-alert-text))]"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading && !stats ? (
        <p className="text-secondary-text">加载中…</p>
      ) : stats ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="内容总数" value={stats.totalContents.toLocaleString()} tone="primary" />
            <StatCard
              label="提取成功率"
              value={formatPct(stats.extractionSuccessRate)}
              hint="相对可处理内容（不含已忽略）"
              tone="success"
            />
            <StatCard
              label="UP主覆盖率"
              value={formatPct(stats.creatorCoverageRate)}
              hint={`${stats.coveredCreators} / ${stats.activeCreators} 活跃源`}
              tone="default"
            />
            <StatCard
              label="失败可解释率"
              value={formatPct(stats.failureExplainabilityRate)}
              hint="失败记录含阶段与原因"
              tone="warning"
            />
          </div>

          <Card title="处理漏斗" padding="md">
            <p className="-mt-1 mb-4 text-sm text-secondary-text">按内容状态占比（横向条）</p>
            {funnelTotal === 0 ? (
              <p className="text-sm text-secondary-text">所选时间范围内暂无内容。</p>
            ) : (
              <>
                <div className="flex h-10 w-full overflow-hidden rounded-xl border border-border/80 bg-muted/50">
                  {segments.map((s) => {
                    const w = funnelTotal > 0 ? (s.count / funnelTotal) * 100 : 0;
                    if (w <= 0) return null;
                    return (
                      <div
                        key={s.key}
                        className={cn(s.className, 'flex min-w-0 items-center justify-center')}
                        style={{ width: `${w}%` }}
                        title={`${s.label}: ${s.count}`}
                      >
                        {w >= 8 ? <span className="truncate px-1 text-[10px] font-medium text-white drop-shadow-sm">{s.label}</span> : null}
                      </div>
                    );
                  })}
                </div>
                <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-secondary-text">
                  {segments.map((s) => (
                    <li key={s.key} className="flex items-center gap-1.5">
                      <span className={cn('h-2 w-2 rounded-sm', s.className)} />
                      <span>
                        {s.label}: <strong className="text-foreground">{s.count}</strong>
                        {funnelTotal ? ` (${((s.count / funnelTotal) * 100).toFixed(1)}%)` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card title="UP主表现" padding="md" className="overflow-hidden">
            <p className="-mt-1 mb-4 text-sm text-secondary-text">活跃 UP 主在时间范围内的采集与提取</p>
            <div className="-mx-5 -mb-5 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-secondary-text">
                  <tr>
                    <th className="px-4 py-3 font-medium">名称</th>
                    <th className="px-4 py-3 font-medium">内容数</th>
                    <th className="px-4 py-3 font-medium">已提取</th>
                    <th className="px-4 py-3 font-medium">失败</th>
                    <th className="px-4 py-3 font-medium">成功率</th>
                    <th className="px-4 py-3 font-medium">最近采集</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {creatorRows.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-secondary-text">
                        暂无数据
                      </td>
                    </tr>
                  ) : (
                    creatorRows.map((row) => (
                      <tr key={row.creatorId} className="bg-card/40 hover:bg-muted/25">
                        <td className="px-4 py-3 font-medium text-foreground">{row.name}</td>
                        <td className="px-4 py-3 text-secondary-text">{row.total}</td>
                        <td className="px-4 py-3 text-secondary-text">{row.extracted}</td>
                        <td className="px-4 py-3 text-secondary-text">{row.failed}</td>
                        <td className="px-4 py-3 text-secondary-text">{formatPct(row.successRate)}</td>
                        <td className="px-4 py-3 whitespace-nowrap text-secondary-text">
                          {formatLastFetch(row.lastFetchAt)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="失败原因" padding="md">
            <p className="-mt-1 mb-4 text-sm text-secondary-text">按出现次数排序</p>
            {failures.length === 0 ? (
              <p className="text-sm text-secondary-text">所选范围内无失败记录。</p>
            ) : (
              <ol className="space-y-3">
                {failures.map((item, idx) => (
                  <li
                    key={`${item.stage ?? ''}-${item.reason ?? ''}-${idx}`}
                    className="flex flex-wrap items-baseline justify-between gap-2 rounded-xl border border-border/60 bg-muted/20 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <span className="text-xs font-semibold text-cyan">#{idx + 1}</span>
                      <span className="ml-2 text-sm text-foreground">{item.reason ?? '—'}</span>
                      {item.stage ? (
                        <span className="mt-1 block text-xs text-secondary-text">阶段：{item.stage}</span>
                      ) : null}
                    </div>
                    <span className="shrink-0 rounded-lg bg-card px-2 py-1 text-sm font-semibold tabular-nums text-foreground">
                      {item.count} 次
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
};

export default QualityDashboard;
