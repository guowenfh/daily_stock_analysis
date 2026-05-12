import { useCallback, useEffect, useMemo, useState } from 'react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { ContentItem, Creator } from '../../types/signal';
import { Card } from '../../components/common';
import { cn } from '../../utils/cn';

const PAGE_SIZE = 25;

const SELECT_CLASS =
  'input-surface input-focus-glow h-10 rounded-xl border border-border/60 bg-transparent px-3 text-sm text-foreground transition-all focus:outline-none';

const STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'collected', label: '已采集' },
  { value: 'pending_enrich', label: '待丰富' },
  { value: 'pending_extract', label: '待提取' },
  { value: 'extracted', label: '已提取' },
  { value: 'low_confidence', label: '低置信' },
  { value: 'failed', label: '失败' },
  { value: 'ignored', label: '已忽略' },
];

const DISPLAY_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部形态' },
  { value: 'video_subtitle', label: '视频字幕' },
  { value: 'image_text', label: '图文' },
  { value: 'text', label: '文本' },
];

function formatPublishTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

function statusBadgeClass(status: string): string {
  if (status === 'extracted' || status === 'low_confidence') {
    return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/25';
  }
  if (status === 'failed') {
    return 'bg-red-500/15 text-red-600 dark:text-red-400 ring-1 ring-red-500/25';
  }
  if (status === 'ignored') {
    return 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-300 ring-1 ring-zinc-500/20';
  }
  return 'bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/25';
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    collected: '已采集',
    pending_enrich: '待丰富',
    pending_extract: '待提取',
    extracted: '已提取',
    low_confidence: '低置信',
    failed: '失败',
    ignored: '已忽略',
  };
  return map[status] ?? status;
}

function guessBilibiliUrl(platformContentId: string): string {
  const id = platformContentId.trim();
  if (/^BV[\w]+$/i.test(id)) return `https://www.bilibili.com/video/${id}`;
  if (/^\d+$/.test(id)) return `https://t.bilibili.com/${id}`;
  return `https://search.bilibili.com/all?keyword=${encodeURIComponent(id)}`;
}

const ContentQueuePage = () => {
  const [rows, setRows] = useState<ContentItem[]>([]);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const [displayType, setDisplayType] = useState('');
  const [creatorId, setCreatorId] = useState<string>('');
  const [page, setPage] = useState(1);
  const [actionId, setActionId] = useState<number | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  const load = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      const cid = creatorId === '' ? undefined : Number(creatorId);
      const data = await signalApi.listContents({
        status: status || undefined,
        displayType: displayType || undefined,
        creatorId: Number.isFinite(cid) ? cid : undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setRows(data);
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [status, displayType, creatorId, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    void signalApi
      .listCreators()
      .then((c) => {
        if (!cancelled) setCreators(c);
      })
      .catch(() => {
        if (!cancelled) setCreators([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setPage(1);
  }, [status, displayType, creatorId]);

  const hasNextPage = rows.length >= PAGE_SIZE;
  const hasPrevPage = page > 1;

  const failureOrQuality = (row: ContentItem) => {
    const parts: string[] = [];
    if (row.failureReason) parts.push(row.failureReason);
    else if (row.failureStage) parts.push(`阶段: ${row.failureStage}`);
    if (row.status === 'low_confidence') parts.push('低置信内容');
    return parts.length ? parts.join(' · ') : '—';
  };

  const creatorOptions = useMemo(
    () => [...creators].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
    [creators]
  );

  const onRetry = async (id: number) => {
    try {
      setActionId(id);
      await signalApi.retryContent(id);
      await load();
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setActionId(null);
    }
  };

  const onIgnore = async (id: number) => {
    try {
      setActionId(id);
      await signalApi.ignoreContent(id);
      await load();
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setActionId(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">内容队列</h1>
        <p className="mt-1 text-sm text-secondary-text">采集内容处理状态、失败诊断与重试</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-secondary-text">
            状态
            <select
              className={cn(SELECT_CLASS, 'min-w-[8.5rem]')}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUS_FILTER_OPTIONS.map((o) => (
                <option key={o.value || 'all'} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-secondary-text">
            内容形态
            <select
              className={cn(SELECT_CLASS, 'min-w-[9rem]')}
              value={displayType}
              onChange={(e) => setDisplayType(e.target.value)}
            >
              {DISPLAY_TYPE_OPTIONS.map((o) => (
                <option key={o.value || 'all-dt'} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-secondary-text">
            UP主
            <select
              className={cn(SELECT_CLASS, 'min-w-[11rem]')}
              value={creatorId}
              onChange={(e) => setCreatorId(e.target.value)}
            >
              <option value="">全部 UP 主</option>
              {creatorOptions.map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-secondary-text">
                <th className="px-4 py-3 font-medium">发布时间</th>
                <th className="px-4 py-3 font-medium">UP主</th>
                <th className="px-4 py-3 font-medium">标题 / 摘要</th>
                <th className="px-4 py-3 font-medium">内容形态</th>
                <th className="px-4 py-3 font-medium">当前状态</th>
                <th className="px-4 py-3 font-medium">失败原因 / 质量标记</th>
                <th className="px-4 py-3 font-medium">已产生信号</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center text-secondary-text">
                    加载中…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center text-secondary-text">
                    暂无数据
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id} className="border-b border-border/60 hover:bg-hover/50">
                    <td className="whitespace-nowrap px-4 py-3 text-foreground">
                      {formatPublishTime(row.publishedAt)}
                    </td>
                    <td className="px-4 py-3 text-foreground">{row.creatorName}</td>
                    <td className="max-w-xs px-4 py-3 text-foreground">
                      <div className="line-clamp-2">{row.title || '（无标题）'}</div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-secondary-text">{row.displayType}</td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex rounded-lg px-2.5 py-1 text-xs font-medium',
                          statusBadgeClass(row.status)
                        )}
                      >
                        {statusLabel(row.status)}
                      </span>
                    </td>
                    <td className="max-w-[14rem] px-4 py-3 text-xs text-secondary-text">
                      {failureOrQuality(row)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span
                        className={cn(
                          'text-sm font-medium',
                          row.hasMentions ? 'text-emerald-600 dark:text-emerald-400' : 'text-secondary-text'
                        )}
                      >
                        {row.hasMentions ? '是' : '否'}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        <a
                          href={guessBilibiliUrl(row.platformContentId)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rounded-lg border border-border/70 px-2.5 py-1 text-xs font-medium text-cyan hover:bg-hover"
                        >
                          查看原文
                        </a>
                        <button
                          type="button"
                          disabled={actionId === row.id}
                          onClick={() => void onRetry(row.id)}
                          className="rounded-lg border border-border/70 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-hover disabled:opacity-50"
                        >
                          重试
                        </button>
                        <button
                          type="button"
                          disabled={actionId === row.id || row.status === 'ignored'}
                          onClick={() => void onIgnore(row.id)}
                          className="rounded-lg border border-border/70 px-2.5 py-1 text-xs font-medium text-secondary-text hover:bg-hover disabled:opacity-50"
                        >
                          忽略
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
          <span className="text-xs text-secondary-text">
            每页 {PAGE_SIZE} 条 · 第 {page} 页
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!hasPrevPage || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium text-foreground hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={!hasNextPage || loading}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium text-foreground hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default ContentQueuePage;
