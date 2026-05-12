import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { AssetDetailOverview, Mention } from '../../types/signal';
import { Card, Collapsible } from '../../components/common';
import { cn } from '../../utils/cn';

const WEIGHT_HIGH = 1.3;

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function confidenceRatio(c: number): number {
  if (!Number.isFinite(c)) return 0;
  return c > 1 ? Math.min(1, c / 100) : Math.min(1, Math.max(0, c));
}

function sentimentBadge(s: string): { label: string; className: string } {
  switch (s) {
    case 'bullish':
      return { label: '看多', className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' };
    case 'bearish':
      return { label: '看空', className: 'bg-red-500/15 text-red-600 dark:text-red-400' };
    case 'neutral':
      return { label: '中性', className: 'bg-slate-500/15 text-slate-600 dark:text-slate-300' };
    default:
      return { label: s, className: 'bg-muted text-secondary-text' };
  }
}

function eventTypeBadge(t: string): { label: string; className: string } {
  switch (t) {
    case 'opportunity':
      return { label: '机会', className: 'bg-emerald-500/15 text-emerald-600 ring-1 ring-emerald-500/25' };
    case 'risk':
      return { label: '风险', className: 'bg-red-500/15 text-red-600 ring-1 ring-red-500/25' };
    case 'conflict':
      return { label: '分歧', className: 'bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30' };
    case 'watch':
      return { label: '观察', className: 'bg-slate-500/15 text-slate-600 ring-1 ring-slate-400/25' };
    default:
      return { label: t, className: 'bg-muted ring-1 ring-border/60' };
  }
}

const AssetDetailPage = () => {
  const { identifier: identifierParam } = useParams<{ identifier: string }>();
  const navigate = useNavigate();
  const identifier = identifierParam ?? '';

  const [overview, setOverview] = useState<AssetDetailOverview | null>(null);
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!identifier) {
      setError('缺少标的标识');
      setOverview(null);
      setMentions([]);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      setLoading(true);
      const [o, m] = await Promise.all([
        signalApi.getAsset(identifier),
        signalApi.getAssetMentions(identifier, { limit: 100, offset: 0 }),
      ]);
      setOverview(o);
      setMentions(m);
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
      setOverview(null);
      setMentions([]);
    } finally {
      setLoading(false);
    }
  }, [identifier]);

  useEffect(() => {
    void load();
  }, [load]);

  const weightByCreator = useMemo(() => {
    const map = new Map<number, number>();
    if (overview?.creators) {
      for (const c of overview.creators) {
        map.set(c.id, c.weight);
      }
    }
    return map;
  }, [overview]);

  const sortedCreators = useMemo(
    () => [...(overview?.creators ?? [])].sort((a, b) => b.weight - a.weight),
    [overview]
  );

  const sentimentBar = overview?.sentimentSummary;
  const totalSent =
    sentimentBar != null
      ? sentimentBar.bullish + sentimentBar.bearish + sentimentBar.neutral
      : 0;

  const mentionHighlight = (m: Mention) => {
    const w = weightByCreator.get(m.creatorId) ?? 1;
    return m.isPrimary || w >= WEIGHT_HIGH;
  };

  if (!identifier) {
    return (
      <div className="p-6">
        <p className="text-secondary-text">无效链接</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="text-sm font-medium text-cyan hover:underline"
      >
        ← 返回
      </button>

      {loading && (
        <Card className="p-10 text-center text-secondary-text">加载中…</Card>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {!loading && overview && (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-foreground">{overview.assetName}</h1>
              {overview.assetCode && (
                <span className="rounded-lg bg-muted/70 px-2 py-1 text-sm text-secondary-text">
                  {overview.assetCode}
                </span>
              )}
              <span className="rounded-lg bg-muted/70 px-2 py-1 text-xs text-secondary-text">
                {overview.assetType}
              </span>
              <span className="rounded-lg bg-muted/70 px-2 py-1 text-xs text-secondary-text">
                {overview.market}
              </span>
              {overview.event && (
                <span
                  className={cn(
                    'inline-flex rounded-lg px-2.5 py-1 text-xs font-semibold',
                    eventTypeBadge(overview.event.eventType).className
                  )}
                >
                  {eventTypeBadge(overview.event.eventType).label}
                </span>
              )}
            </div>
            {overview.event && (
              <p className="text-sm text-secondary-text">
                事件日 {overview.event.eventDate}
                {overview.event.score != null ? ` · 得分 ${overview.event.score.toFixed(1)}` : ''}
              </p>
            )}
          </div>

          <Card className="p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-secondary-text">多空结构</p>
            {totalSent > 0 && sentimentBar ? (
              <>
                <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="bg-emerald-500/90"
                    style={{ width: `${(sentimentBar.bullish / totalSent) * 100}%` }}
                    title={`看多 ${sentimentBar.bullish}`}
                  />
                  <div
                    className="bg-red-500/90"
                    style={{ width: `${(sentimentBar.bearish / totalSent) * 100}%` }}
                    title={`看空 ${sentimentBar.bearish}`}
                  />
                  <div
                    className="bg-slate-400/80"
                    style={{ width: `${(sentimentBar.neutral / totalSent) * 100}%` }}
                    title={`中性 ${sentimentBar.neutral}`}
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-secondary-text">
                  <span className="text-emerald-600 dark:text-emerald-400">看多 {sentimentBar.bullish}</span>
                  <span className="text-red-600 dark:text-red-400">看空 {sentimentBar.bearish}</span>
                  <span>中性 {sentimentBar.neutral}</span>
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-secondary-text">暂无结构化多空计数</p>
            )}
          </Card>

          <Card className="p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-secondary-text">
              涉及的 UP 主（权重）
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {sortedCreators.length === 0 ? (
                <span className="text-sm text-secondary-text">—</span>
              ) : (
                sortedCreators.map((c) => (
                  <span
                    key={c.id}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm',
                      c.weight >= WEIGHT_HIGH
                        ? 'border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200'
                        : 'border-border/60 bg-card text-foreground'
                    )}
                  >
                    <span className="font-medium">{c.name}</span>
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-secondary-text">
                      {c.weight.toFixed(1)}
                    </span>
                  </span>
                ))
              )}
            </div>
          </Card>

          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-foreground">观点提及</h2>
            {mentions.length === 0 ? (
              <Card className="p-8 text-center text-secondary-text">暂无提及</Card>
            ) : (
              mentions.map((m) => {
                const sent = sentimentBadge(m.sentiment);
                const ratio = confidenceRatio(m.confidence);
                const high = mentionHighlight(m);
                const w = weightByCreator.get(m.creatorId) ?? 1;
                return (
                  <Card
                    key={m.id}
                    className={cn(
                      'p-4 transition-colors',
                      high && 'ring-1 ring-amber-500/35 bg-amber-500/[0.04]'
                    )}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-foreground">{m.creatorName}</span>
                          <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-secondary-text">
                            权重 {w.toFixed(1)}
                          </span>
                          {m.isPrimary && (
                            <span className="rounded-md bg-cyan/15 px-2 py-0.5 text-xs font-medium text-cyan">
                              主提及
                            </span>
                          )}
                          <span className={cn('rounded-md px-2 py-0.5 text-xs font-medium', sent.className)}>
                            {sent.label}
                          </span>
                        </div>
                        <p className="text-sm text-foreground">
                          内容 <span className="text-secondary-text">#{m.contentId}</span>
                          {high && (
                            <span className="ml-2 text-xs font-medium text-amber-600 dark:text-amber-400">
                              高权重 / 重点
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-secondary-text">发布时间 {formatDateTime(m.publishedAt)}</p>
                      </div>
                      <div className="w-full shrink-0 sm:w-48">
                        <div className="flex justify-between text-xs text-secondary-text">
                          <span>置信度</span>
                          <span>{(ratio * 100).toFixed(0)}%</span>
                        </div>
                        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-cyan/80"
                            style={{ width: `${ratio * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    {m.reasoning && (
                      <div className="mt-3">
                        <Collapsible title="推理依据" defaultOpen={high}>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-secondary-text">
                            {m.reasoning}
                          </p>
                        </Collapsible>
                      </div>
                    )}

                    {m.tradeAdvice && (
                      <div className="mt-3 rounded-xl border border-border/50 bg-muted/30 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-secondary-text">
                          交易建议摘要
                        </p>
                        <p className="mt-1 text-sm text-foreground">{m.tradeAdvice}</p>
                      </div>
                    )}

                    {m.keyLevels && Object.keys(m.keyLevels).length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-semibold text-secondary-text">关键价位</p>
                        <ul className="mt-1 space-y-1 text-sm text-foreground">
                          {Object.entries(m.keyLevels).map(([k, vals]) => (
                            <li key={k}>
                              <span className="text-secondary-text">{k}: </span>
                              {vals.join(', ')}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {m.qualityFlags.map((f) => (
                        <span
                          key={f}
                          className="rounded-md border border-border/60 bg-card px-2 py-0.5 text-[11px] text-secondary-text"
                        >
                          {f}
                        </span>
                      ))}
                    </div>

                    {m.sourceUrl && (
                      <div className="mt-3">
                        <a
                          href={m.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-cyan hover:underline"
                        >
                          查看原文
                        </a>
                      </div>
                    )}
                  </Card>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default AssetDetailPage;
