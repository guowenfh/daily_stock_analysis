import { useCallback, useEffect, useState } from 'react';
import { signalApi } from '../../api/signal';
import type { QualityStats } from '../../types/signal';
import { cn } from '../../utils/cn';

function formatTime(d: Date): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(d);
}

const StatusBar = () => {
  const [stats, setStats] = useState<QualityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const s = await signalApi.getOverviewStats(1);
      setStats(s);
      setUpdatedAt(new Date());
    } catch {
      setStats(null);
      setUpdatedAt(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const covered = stats?.coveredCreators ?? '—';
  const active = stats?.activeCreators ?? '—';
  const signalCount = stats?.signalEventCount ?? '—';

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-border/70 bg-card/60 px-4 py-3 text-sm',
        'text-foreground dark:border-border/80 dark:bg-card/50'
      )}
    >
      <span className="text-secondary-text">
        今日覆盖{' '}
        <span className="font-semibold text-foreground">
          {loading ? '…' : `${covered}/${active}`}
        </span>{' '}
        位创作者
      </span>
      <span className="hidden text-border sm:inline" aria-hidden>
        ·
      </span>
      <span className="text-secondary-text">
        <span className="font-semibold text-foreground">
          {loading ? '…' : signalCount}
        </span>{' '}
        条信号
      </span>
      <span className="hidden text-border sm:inline" aria-hidden>
        ·
      </span>
      <span className="text-secondary-text">
        最近更新{' '}
        <span className="font-medium text-foreground">
          {updatedAt ? formatTime(updatedAt) : '—'}
        </span>
      </span>
    </div>
  );
};

export default StatusBar;
