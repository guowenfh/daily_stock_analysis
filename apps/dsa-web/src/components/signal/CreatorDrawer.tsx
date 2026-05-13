import { X } from 'lucide-react';
import type { Creator } from '../../types/signal';
import ContentQueuePage from '../../pages/signal/ContentQueuePage';
import { cn } from '../../utils/cn';

export type CreatorDrawerProps = {
  creator: Creator | null;
  onClose: () => void;
};

const CreatorDrawer = ({ creator, onClose }: CreatorDrawerProps) => {
  const open = creator != null;

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/40 transition-opacity duration-200',
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={onClose}
        aria-hidden
      />

      {/* Drawer */}
      <div
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-3xl flex-col border-l border-border/60 bg-base shadow-2xl transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
        role="dialog"
        aria-modal="true"
        aria-label={creator ? `${creator.name} 动态时间线` : ''}
      >
        {creator && (
          <>
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border/40 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{creator.name}</h2>
                <p className="mt-0.5 text-xs text-secondary-text">
                  {creator.platform} · UID {creator.platformUid}
                  {creator.category ? ` · ${creator.category}` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-1.5 text-secondary-text hover:bg-hover hover:text-foreground"
                aria-label="关闭"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content queue filtered by this creator */}
            <div className="flex-1 overflow-y-auto p-4">
              <ContentQueuePage fixedCreatorId={creator.id} compact />
            </div>
          </>
        )}
      </div>
    </>
  );
};

export default CreatorDrawer;
