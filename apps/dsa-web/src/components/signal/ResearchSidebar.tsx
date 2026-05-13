import { useCallback, useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { AssetDetailOverview, Mention, SignalEvent } from '../../types/signal';
import { cn } from '../../utils/cn';
import CreatorTimeline from './CreatorTimeline';
import ContentViewer from './ContentViewer';

function sentimentBarClass(s: string): { label: string; segmentClass: string; pillClass: string } {
  switch (s) {
    case 'bullish':
      return {
        label: '看多',
        segmentClass: 'bg-emerald-500 dark:bg-emerald-500',
        pillClass:
          'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-500/25',
      };
    case 'bearish':
      return {
        label: '看空',
        segmentClass: 'bg-red-500 dark:bg-red-500',
        pillClass: 'bg-red-500/15 text-red-700 dark:text-red-400 ring-1 ring-red-500/25',
      };
    case 'neutral':
      return {
        label: '中性',
        segmentClass: 'bg-slate-400 dark:bg-slate-500',
        pillClass:
          'bg-slate-500/15 text-slate-700 dark:text-slate-300 ring-1 ring-slate-400/25',
      };
    default:
      return {
        label: s,
        segmentClass: 'bg-zinc-400 dark:bg-zinc-500',
        pillClass: 'bg-muted text-secondary-text ring-1 ring-border/60',
      };
  }
}

function confidencePct(c: number): string {
  if (!Number.isFinite(c)) return '—';
  const v = c > 1 ? c : c * 100;
  return `${Math.round(v)}%`;
}

function mentionSentimentCounts(mentions: Mention[]) {
  let bullish = 0;
  let bearish = 0;
  let neutral = 0;
  for (const m of mentions) {
    if (m.sentiment === 'bullish') bullish += 1;
    else if (m.sentiment === 'bearish') bearish += 1;
    else neutral += 1;
  }
  return { bullish, bearish, neutral };
}

function formatFlags(flags: string[]): string {
  if (!flags.length) return '—';
  const map: Record<string, string> = {
    based_on_summary: '基于摘要',
  };
  return flags.map((f) => map[f] ?? f).join('、');
}

export type ResearchSidebarProps = {
  open: boolean;
  event: SignalEvent | null;
  identifier: string | null;
  onClose: () => void;
};

const ResearchSidebar = ({ open, event, identifier, onClose }: ResearchSidebarProps) => {
  const [overview, setOverview] = useState<AssetDetailOverview | null>(null);
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!identifier) {
      setOverview(null);
      setMentions([]);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const [o, m] = await Promise.all([
        signalApi.getAsset(identifier),
        signalApi.getAssetMentions(identifier, { includeContent: true, limit: 200, offset: 0 }),
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
    if (open && identifier) void load();
  }, [open, identifier, load]);

  const weightByCreator = useMemo(() => {
    const m = new Map<number, number>();
    for (const c of overview?.creators ?? []) {
      m.set(c.id, c.weight);
    }
    return m;
  }, [overview]);

  const sentiment = useMemo(() => {
    if (overview?.sentimentSummary) return overview.sentimentSummary;
    return mentionSentimentCounts(mentions);
  }, [overview, mentions]);

  const totalS = sentiment.bullish + sentiment.bearish + sentiment.neutral;
  const bullPct = totalS > 0 ? (sentiment.bullish / totalS) * 100 : 0;
  const neuPct = totalS > 0 ? (sentiment.neutral / totalS) * 100 : 0;
  const bearPct = totalS > 0 ? (sentiment.bearish / totalS) * 100 : 0;

  const headerName = event?.assetName ?? overview?.assetName ?? '—';
  const headerCode = event?.assetCode ?? overview?.assetCode;
  const headerType = event?.assetType ?? overview?.assetType ?? '—';
  const headerMarket = event?.market ?? overview?.market ?? '—';

  const sortedDetails = useMemo(
    () =>
      [...mentions].sort((a, b) => {
        const wa = weightByCreator.get(a.creatorId) ?? 1;
        const wb = weightByCreator.get(b.creatorId) ?? 1;
        if (wb !== wa) return wb - wa;
        const ta = a.publishedAt ?? a.createdAt ?? '';
        const tb = b.publishedAt ?? b.createdAt ?? '';
        return tb.localeCompare(ta);
      }),
    [mentions, weightByCreator]
  );

  return (
    <AnimatePresence>
      {open ? (
        <>
          <motion.button
            type="button"
            aria-label="关闭侧栏"
            className="fixed inset-0 z-40 bg-black/40 dark:bg-black/55"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label="标的研判"
            className={cn(
              'fixed top-0 right-0 z-50 flex h-full w-full max-w-[420px] flex-col border-l border-border/80 bg-base shadow-2xl',
              'dark:border-border'
            )}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 320 }}
          >
            <div className="flex items-start justify-between gap-3 border-b border-border/70 p-4 dark:border-border/80">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-semibold text-foreground">{headerName}</h2>
                <p className="mt-1 text-xs text-secondary-text">
                  {[headerCode, headerType, headerMarket].filter(Boolean).join(' · ')}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-2 text-secondary-text hover:bg-hover hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {error ? (
                <div className="mb-4 rounded-xl border border-red-500/35 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                  {error}
                </div>
              ) : null}

              {loading ? (
                <p className="text-sm text-secondary-text">加载中…</p>
              ) : (
                <>
                  <div className="mb-4">
                    <p className="mb-2 text-xs font-medium text-secondary-text">情绪分布</p>
                    <div className="flex h-3 overflow-hidden rounded-full bg-muted/50 dark:bg-muted/30">
                      {bullPct > 0 ? (
                        <div
                          className={sentimentBarClass('bullish').segmentClass}
                          style={{ width: `${bullPct}%` }}
                          title={`看多 ${sentiment.bullish}`}
                        />
                      ) : null}
                      {neuPct > 0 ? (
                        <div
                          className={sentimentBarClass('neutral').segmentClass}
                          style={{ width: `${neuPct}%` }}
                          title={`中性 ${sentiment.neutral}`}
                        />
                      ) : null}
                      {bearPct > 0 ? (
                        <div
                          className={sentimentBarClass('bearish').segmentClass}
                          style={{ width: `${bearPct}%` }}
                          title={`看空 ${sentiment.bearish}`}
                        />
                      ) : null}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-secondary-text">
                      <span>
                        看多 <span className="font-medium text-foreground">{sentiment.bullish}</span>
                      </span>
                      <span>
                        中性 <span className="font-medium text-foreground">{sentiment.neutral}</span>
                      </span>
                      <span>
                        看空 <span className="font-medium text-foreground">{sentiment.bearish}</span>
                      </span>
                    </div>
                  </div>

                  <div className="mb-6">
                    <p className="mb-2 text-xs font-medium text-secondary-text">按 UP 主</p>
                    <CreatorTimeline mentions={mentions} weightByCreator={weightByCreator} />
                  </div>

                  <div className="space-y-3">
                    <p className="text-xs font-medium text-secondary-text">提及详情</p>
                    {sortedDetails.map((m) => {
                      const sb = sentimentBarClass(m.sentiment);
                      return (
                        <div
                          key={m.id}
                          className={cn(
                            'space-y-3 rounded-2xl border border-border/70 bg-card/60 p-3 dark:border-border/80 dark:bg-card/40'
                          )}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-foreground">{m.creatorName}</span>
                            <span className={cn('rounded-md px-2 py-0.5 text-xs font-medium', sb.pillClass)}>
                              {sb.label}
                            </span>
                            <span className="text-xs text-secondary-text">
                              置信 {confidencePct(m.confidence)}
                            </span>
                          </div>
                          {m.reasoning ? (
                            <div>
                              <p className="text-xs font-medium text-secondary-text">推理</p>
                              <p className="mt-0.5 text-sm text-foreground">{m.reasoning}</p>
                            </div>
                          ) : null}
                          {m.tradeAdvice ? (
                            <div>
                              <p className="text-xs font-medium text-secondary-text">交易建议</p>
                              <p className="mt-0.5 text-sm text-foreground">{m.tradeAdvice}</p>
                            </div>
                          ) : null}
                          <div>
                            <p className="text-xs font-medium text-secondary-text">质量标记</p>
                            <p className="mt-0.5 text-sm text-foreground">{formatFlags(m.qualityFlags)}</p>
                          </div>
                          <ContentViewer mention={m} />
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
};

export default ResearchSidebar;
