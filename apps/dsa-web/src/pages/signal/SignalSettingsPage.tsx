import { useCallback, useEffect, useMemo } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { cn } from '../../utils/cn';
import CreatorManagePage from './CreatorManagePage';
import QualityDashboard from './QualityDashboard';
import ContentQueuePage from './ContentQueuePage';

type SettingsTab = 'creators' | 'quality' | 'content';

const TAB_CONFIG: { key: SettingsTab; label: string }[] = [
  { key: 'creators', label: 'UP主管理' },
  { key: 'quality', label: '采集质量' },
  { key: 'content', label: '内容队列' },
];

function parseTab(raw: string | null): SettingsTab {
  if (raw === 'quality' || raw === 'content' || raw === 'creators') return raw;
  return 'creators';
}

const SignalSettingsPage = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const tab = useMemo(() => parseTab(search.get('tab')), [search]);

  useEffect(() => {
    const raw = search.get('tab');
    if (raw != null && raw !== 'creators' && raw !== 'quality' && raw !== 'content') {
      const next = new URLSearchParams(search);
      next.set('tab', 'creators');
      setSearch(next, { replace: true });
    }
  }, [search, setSearch]);

  const setTab = useCallback(
    (next: SettingsTab) => {
      const p = new URLSearchParams(search);
      p.set('tab', next);
      setSearch(p, { replace: false });
    },
    [search, setSearch]
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/signals')}
            className="inline-flex items-center justify-center rounded-xl border border-border/60 p-2 text-secondary-text hover:bg-hover hover:text-foreground"
            aria-label="返回简报"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-foreground">信号设置</h1>
            <p className="mt-1 text-sm text-secondary-text">采集源、质量与内容处理</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border/60 pb-3 dark:border-border/80">
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

      <div className="min-h-[50vh]">
        {tab === 'creators' ? <CreatorManagePage /> : null}
        {tab === 'quality' ? <QualityDashboard /> : null}
        {tab === 'content' ? <ContentQueuePage /> : null}
      </div>
    </div>
  );
};

export default SignalSettingsPage;
