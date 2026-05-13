import { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import type { Mention } from '../../types/signal';
import { cn } from '../../utils/cn';

function expandToggle(open: boolean) {
  return open ? (
    <ChevronDown className="h-4 w-4 shrink-0 text-secondary-text" />
  ) : (
    <ChevronRight className="h-4 w-4 shrink-0 text-secondary-text" />
  );
}

export type ContentViewerProps = {
  mention: Mention;
};

const ContentViewer = ({ mention }: ContentViewerProps) => {
  const [sourceOpen, setSourceOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const body =
    mention.contentText?.trim() ||
    mention.transcriptText?.trim() ||
    '';
  const hasSummary =
    mention.qualityFlags.includes('based_on_summary') && Boolean(mention.summaryText?.trim());
  const showSource = Boolean(body);

  return (
    <div className="space-y-2 text-sm">
      {showSource ? (
        <div className="overflow-hidden rounded-xl border border-border/60 bg-muted/20 dark:bg-muted/10">
          <button
            type="button"
            onClick={() => setSourceOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left font-medium text-foreground hover:bg-hover"
          >
            <span>原文内容</span>
            {expandToggle(sourceOpen)}
          </button>
          {sourceOpen ? (
            <div className="max-h-64 overflow-y-auto border-t border-border/50 px-3 py-2 text-secondary-text whitespace-pre-wrap">
              {body}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasSummary ? (
        <div className="overflow-hidden rounded-xl border border-border/60 bg-muted/20 dark:bg-muted/10">
          <button
            type="button"
            onClick={() => setSummaryOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left font-medium text-foreground hover:bg-hover"
          >
            <span>摘要</span>
            {expandToggle(summaryOpen)}
          </button>
          {summaryOpen ? (
            <div className="max-h-48 overflow-y-auto border-t border-border/50 px-3 py-2 text-secondary-text whitespace-pre-wrap">
              {mention.summaryText}
            </div>
          ) : null}
        </div>
      ) : null}

      {mention.sourceUrl ? (
        <a
          href={mention.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'inline-flex items-center gap-1.5 text-sm font-medium text-cyan hover:underline',
            'dark:text-cyan/90'
          )}
        >
          <ExternalLink className="h-4 w-4" />
          打开来源
        </a>
      ) : null}
    </div>
  );
};

export default ContentViewer;
