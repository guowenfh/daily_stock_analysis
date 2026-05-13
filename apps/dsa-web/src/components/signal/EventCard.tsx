import type { SignalEvent } from '../../types/signal';
import { cn } from '../../utils/cn';

const EVENT_TYPE_META: Record<
  string,
  { label: string; icon: string; className: string }
> = {
  opportunity: {
    label: '机会',
    icon: '🟢',
    className:
      'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/25',
  },
  risk: {
    label: '风险',
    icon: '🔴',
    className: 'bg-red-500/15 text-red-600 dark:text-red-400 ring-1 ring-red-500/25',
  },
  conflict: {
    label: '分歧',
    icon: '🟡',
    className:
      'bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/30',
  },
  watch: {
    label: '观察',
    icon: '⚪',
    className:
      'bg-slate-500/15 text-slate-600 dark:text-slate-300 ring-1 ring-slate-400/25',
  },
};

function typeMeta(eventType: string) {
  return (
    EVENT_TYPE_META[eventType] ?? {
      label: eventType,
      icon: '◆',
      className: 'bg-zinc-500/10 text-secondary-text ring-1 ring-border/60',
    }
  );
}

export type EventCardProps = {
  event: SignalEvent;
  onClick: () => void;
  isSelected?: boolean;
  showTypeLabel?: boolean;
};

const EventCard = ({ event, onClick, isSelected, showTypeLabel = true }: EventCardProps) => {
  const meta = typeMeta(event.eventType);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-col gap-1.5 rounded-xl border bg-card/80 p-3 text-left transition-all hover:border-cyan/25 hover:bg-card',
        isSelected
          ? 'border-cyan/50 ring-2 ring-cyan/30'
          : 'border-border/70'
      )}
    >
      {/* Top row: type badge + score */}
      <div className="flex items-center justify-between gap-2">
        {showTypeLabel ? (
          <span
            className={cn(
              'inline-flex shrink-0 items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-medium',
              meta.className
            )}
          >
            <span aria-hidden>{meta.icon}</span>
            {meta.label}
          </span>
        ) : (
          <span />
        )}
        <span className="text-xs font-semibold text-foreground">
          {event.score != null ? event.score.toFixed(1) : '—'}
          <span className="ml-0.5 font-normal text-secondary-text">分</span>
        </span>
      </div>

      {/* Asset name */}
      <span className="truncate text-sm font-semibold text-foreground">
        {event.assetName}
      </span>

      {/* Bottom row: code + stats */}
      <div className="flex items-center gap-2 text-[11px] text-secondary-text">
        {event.assetCode ? (
          <span className="rounded bg-muted/60 px-1 py-0.5">
            {event.assetCode}
          </span>
        ) : null}
        <span>{event.creatorCount}UP · {event.mentionCount}提及</span>
      </div>
    </button>
  );
};

export default EventCard;
