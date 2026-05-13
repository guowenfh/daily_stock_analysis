import { useCallback, useEffect, useState } from 'react';
import { signalApi, getSignalApiErrorMessage } from '../../api/signal';
import type { Creator, CreatorCreate, CreatorUpdate } from '../../types/signal';
import { Card } from '../../components/common';
import { cn } from '../../utils/cn';

const INPUT_CLASS =
  'input-surface input-focus-glow h-10 w-full rounded-xl border bg-transparent px-3 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

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

function weightPercent(w: number): number {
  return Math.min(100, Math.max(0, ((w - 0.1) / (2.0 - 0.1)) * 100));
}

const ToggleSwitch = ({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    disabled={disabled}
    onClick={onChange}
    className={cn(
      'relative inline-flex h-7 w-11 shrink-0 rounded-full border border-border/60 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:opacity-50',
      checked ? 'bg-[hsl(var(--color-success)/0.35)]' : 'bg-muted'
    )}
  >
    <span
      className={cn(
        'pointer-events-none absolute top-0.5 h-5 w-5 rounded-full bg-card shadow-sm ring-1 ring-border transition-transform',
        checked ? 'translate-x-[1.35rem]' : 'translate-x-0.5'
      )}
    />
  </button>
);

const CreatorManagePage = () => {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editing, setEditing] = useState<Creator | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const [addForm, setAddForm] = useState({
    platformUid: '',
    name: '',
    category: '',
    manualWeight: 1,
  });
  const [editForm, setEditForm] = useState({
    name: '',
    category: '',
    manualWeight: 1,
    notes: '',
  });

  const loadCreators = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      const data = await signalApi.listCreators();
      setCreators(data);
    } catch (err) {
      console.error('Failed to load creators', err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCreators();
  }, [loadCreators]);

  const openAddModal = () => {
    setAddForm({ platformUid: '', name: '', category: '', manualWeight: 1 });
    setError(null);
    setShowAddModal(true);
  };

  const openEdit = (c: Creator) => {
    setEditForm({
      name: c.name,
      category: c.category ?? '',
      manualWeight: c.manualWeight,
      notes: c.notes ?? '',
    });
    setEditing(c);
    setError(null);
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: CreatorCreate = {
      platformUid: addForm.platformUid.trim(),
      name: addForm.name.trim(),
      category: addForm.category.trim() || undefined,
      manualWeight: addForm.manualWeight,
    };
    if (!payload.platformUid || !payload.name) {
      setError('请填写平台 UID 与名称');
      return;
    }
    try {
      setPendingId(-1);
      setError(null);
      await signalApi.createCreator(payload);
      setShowAddModal(false);
      await loadCreators();
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setPendingId(null);
    }
  };

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    const payload: CreatorUpdate = {
      name: editForm.name.trim() || undefined,
      category: editForm.category.trim() || undefined,
      manualWeight: editForm.manualWeight,
      notes: editForm.notes.trim() || null,
    };
    try {
      setPendingId(editing.id);
      setError(null);
      await signalApi.updateCreator(editing.id, payload);
      setEditing(null);
      await loadCreators();
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
    } finally {
      setPendingId(null);
    }
  };

  const handleToggle = async (c: Creator) => {
    try {
      setPendingId(c.id);
      setError(null);
      const updated = await signalApi.updateCreator(c.id, { isActive: !c.isActive });
      setCreators((prev) => prev.map((x) => (x.id === c.id ? updated : x)));
    } catch (err) {
      console.error(err);
      setError(getSignalApiErrorMessage(err));
      await loadCreators();
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">UP主管理</h1>
          <p className="mt-1 text-sm text-secondary-text">维护采集源、权重与启用状态</p>
        </div>
        <button type="button" onClick={openAddModal} className="btn-primary whitespace-nowrap">
          新增 UP主
        </button>
      </div>

      {error ? (
        <div
          className="rounded-xl border border-danger/40 bg-danger/8 px-4 py-3 text-sm text-[hsl(var(--color-danger-alert-text))]"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <Card variant="default" padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-secondary-text">
              <tr>
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">UID</th>
                <th className="px-4 py-3 font-medium">平台</th>
                <th className="px-4 py-3 font-medium">启用状态</th>
                <th className="px-4 py-3 font-medium">分类</th>
                <th className="px-4 py-3 font-medium">权重</th>
                <th className="px-4 py-3 font-medium">最近采集</th>
                <th className="px-4 py-3 font-medium">备注</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-secondary-text">
                    加载中…
                  </td>
                </tr>
              ) : creators.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-secondary-text">
                    暂无 UP主，请点击「新增」添加
                  </td>
                </tr>
              ) : (
                creators.map((c) => (
                  <tr key={c.id} className="bg-card/40 hover:bg-muted/25">
                    <td className="px-4 py-3 font-medium text-foreground">{c.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-secondary-text">{c.platformUid}</td>
                    <td className="px-4 py-3 text-secondary-text">
                      <span className="rounded-lg bg-muted px-2 py-0.5 text-xs">{c.platform}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <ToggleSwitch
                          checked={c.isActive}
                          disabled={pendingId === c.id}
                          onChange={() => void handleToggle(c)}
                        />
                        <span className="text-xs text-secondary-text">{c.isActive ? '启用' : '停用'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-secondary-text">{c.category ?? '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex min-w-[120px] flex-col gap-1">
                        <div className="flex items-center justify-between gap-2 text-xs text-secondary-text">
                          <span>{c.manualWeight.toFixed(1)}</span>
                          <span className="text-[10px] text-muted-text">0.1–2.0</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-cyan to-[hsl(var(--color-success))]"
                            style={{ width: `${weightPercent(c.manualWeight)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-secondary-text">{formatLastFetch(c.lastFetchAt)}</td>
                    <td className="max-w-[200px] truncate px-4 py-3 text-secondary-text" title={c.notes ?? ''}>
                      {c.notes?.trim() ? c.notes : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="btn-secondary px-3 py-1.5 text-xs"
                        disabled={pendingId === c.id}
                        onClick={() => openEdit(c)}
                      >
                        编辑
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showAddModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-foreground">新增 UP主</h2>
            <form className="mt-4 space-y-4" onSubmit={(e) => void handleAdd(e)}>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">平台 UID</label>
                <input
                  className={INPUT_CLASS}
                  value={addForm.platformUid}
                  onChange={(e) => setAddForm((s) => ({ ...s, platformUid: e.target.value }))}
                  placeholder="B站 UID 等"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">名称</label>
                <input
                  className={INPUT_CLASS}
                  value={addForm.name}
                  onChange={(e) => setAddForm((s) => ({ ...s, name: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">分类（可选）</label>
                <input
                  className={INPUT_CLASS}
                  value={addForm.category}
                  onChange={(e) => setAddForm((s) => ({ ...s, category: e.target.value }))}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">
                  权重 ({addForm.manualWeight.toFixed(1)}）{' '}
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={2}
                  step={0.1}
                  className="mt-1 w-full accent-cyan"
                  value={addForm.manualWeight}
                  onChange={(e) => setAddForm((s) => ({ ...s, manualWeight: Number(e.target.value) }))}
                />
              </div>
              <p className="text-xs text-muted-text">平台默认为 bilibili；创建后可在后端或后续版本扩展更多平台字段。</p>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={pendingId === -1}
                  onClick={() => setShowAddModal(false)}
                >
                  取消
                </button>
                <button type="submit" className="btn-primary" disabled={pendingId === -1}>
                  {pendingId === -1 ? '保存中…' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-foreground">编辑 — {editing.name}</h2>
            <form className="mt-4 space-y-4" onSubmit={(e) => void handleEditSave(e)}>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">名称</label>
                <input
                  className={INPUT_CLASS}
                  value={editForm.name}
                  onChange={(e) => setEditForm((s) => ({ ...s, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">分类</label>
                <input
                  className={INPUT_CLASS}
                  value={editForm.category}
                  onChange={(e) => setEditForm((s) => ({ ...s, category: e.target.value }))}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">
                  权重 ({editForm.manualWeight.toFixed(1)}）
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={2}
                  step={0.1}
                  className="mt-1 w-full accent-cyan"
                  value={editForm.manualWeight}
                  onChange={(e) => setEditForm((s) => ({ ...s, manualWeight: Number(e.target.value) }))}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-secondary-text">备注</label>
                <textarea
                  className={cn(INPUT_CLASS, 'min-h-[88px] resize-y py-2')}
                  value={editForm.notes}
                  onChange={(e) => setEditForm((s) => ({ ...s, notes: e.target.value }))}
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={pendingId === editing.id}
                  onClick={() => setEditing(null)}
                >
                  取消
                </button>
                <button type="submit" className="btn-primary" disabled={pendingId === editing.id}>
                  {pendingId === editing.id ? '保存中…' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default CreatorManagePage;
