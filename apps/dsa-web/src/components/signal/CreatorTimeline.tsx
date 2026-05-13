import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Mention } from '../../types/signal';
import { cn } from '../../utils/cn';

function sentimentLabel(s: string): string {
  switch (s) {
    case 'bullish':
      return '看多';
    case 'bearish':
      return '看空';
    case 'neutral':
      return '中性';
    default:
      return s;
  }
}

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function confidencePct(c: number): string {
  if (!Number.isFinite(c)) return '—';
  const v = c > 1 ? c : c * 100;
  return `${Math.round(v)}%`;
}

export type CreatorTimelineProps = {
  mentions: Mention[];
  weightByCreator: Map<number, number>;
};

const CreatorTimeline = ({ mentions, weightByCreator }: CreatorTimelineProps) => {
  const [openIds, setOpenIds] = useState<Set<number>>(() => new Set());

  const groups = useMemo(() => {
    const byCreator = new Map<number, Mention[]>();
    for (const m of mentions) {
      const list = byCreator.get(m.creatorId) ?? [];
      list.push(m);
      byCreator.set(m.creatorId, list);
    }
    for (const [, list] of byCreator) {
      list.sort((a, b) => {
        const ta = a.publishedAt ?? a.createdAt ?? '';
        const tb = b.publishedAt ?? b.createdAt ?? '';
        return tb.localeCompare(ta);
      });
    }
    const rows = [...byCreator.entries()].map(([creatorId, ms]) => ({
      creatorId,
      name: ms[0]?.creatorName ?? `ID ${creatorId}`,
      weight: weightByCreator.get(creatorId) ?? 1,
      mentions: ms,
    }));
    rows.sort((a, b) => b.weight - a.weight || a.name.localeCompare(b.name));
    return rows;
  }, [mentions, weightByCreator]);

  const toggle = (id: number) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (groups.length === 0) {
    return <p className="text-sm text-secondary-text">暂无提及</p>;
  }

  return (
    <div className="space-y-2">
      {groups.map((g) => {
        const open = openIds.has(g.creatorId);
        return (
          <div
            key={g.creatorId}
            className="overflow-hidden rounded-xl border border-border/60 bg-muted/15 dark:bg-muted/10"
          >
            <button
              type="button"
              onClick={() => toggle(g.creatorId)}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-hover"
            >
              <span className="min-w-0 truncate font-medium text-foreground">
                {g.name}
                <span className="ml-2 text-xs font-normal text-secondary-text">
                  权重 {g.weight.toFixed(2)} · {g.mentions.length} 条
                </span>
              </span>
              {open ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-secondary-text" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-secondary-text" />
              )}
            </button>
            {open ? (
              <ul className="space-y-2 border-t border-border/50 px-3 py-2">
                {g.mentions.map((m) => (
                  <li
                    key={m.id}
                    className={cn(
                      'rounded-lg border border-border/40 bg-card/50 px-2 py-1.5 text-xs',
                      'dark:border-border/50 dark:bg-card/40'
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-secondary-text">
                      <span>{formatWhen(m.publishedAt ?? m.createdAt)}</span>
                      <span
                        className={cn(
                          'font-medium',
                          m.sentiment === 'bullish' && 'text-emerald-600 dark:text-emerald-400',
                          m.sentiment === 'bearish' && 'text-red-600 dark:text-red-400',
                          m.sentiment === 'neutral' && 'text-slate-600 dark:text-slate-300'
                        )}
                      >
                        {sentimentLabel(m.sentiment)}
                      </span>
                      <span>置信 {confidencePct(m.confidence)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

export default CreatorTimeline;
