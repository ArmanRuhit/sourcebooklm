"use client";

import { useEffect, useRef } from "react";
import { ExternalLinkIcon } from "lucide-react";

import { useSourceContent } from "@/hooks/use-source-content";
import type { Source } from "@/lib/api";

type TextSourceViewerProps = {
  source: Source;
  highlightStart?: number | null;
  highlightEnd?: number | null;
  snippet?: string | null;
};

export function TextSourceViewer({
  source,
  highlightStart = null,
  highlightEnd = null,
  snippet = null,
}: TextSourceViewerProps) {
  const state = useSourceContent(source.id);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (state.status === "ready") {
      markRef.current?.scrollIntoView({ block: "center" });
    }
  }, [state.status, highlightStart, highlightEnd]);

  const originalUrl =
    typeof source.config.url === "string" ? source.config.url : null;

  if (state.status === "loading") {
    return (
      <p className="p-6 text-center text-sm text-muted-foreground">
        Loading source text...
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <p className="p-6 text-center text-sm text-destructive">
        {state.message}
      </p>
    );
  }

  const text = state.content.text ?? "No stored text for this source.";
  const hasHighlight =
    highlightStart !== null &&
    highlightEnd !== null &&
    highlightStart >= 0 &&
    highlightEnd > highlightStart &&
    highlightStart < text.length;
  const end = hasHighlight ? Math.min(highlightEnd, text.length) : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">
          {source.char_count?.toLocaleString() ?? 0} characters
        </span>
        {originalUrl && (
          <a
            href={originalUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Open original
            <ExternalLinkIcon className="size-3" />
          </a>
        )}
      </div>

      {snippet && (
        <div className="border-b bg-amber-50 px-4 py-2.5">
          <p className="text-[11px] font-medium tracking-wide text-amber-900 uppercase">
            Cited passage
          </p>
          <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-amber-950">
            {snippet}
          </p>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        <div className="mx-auto max-w-2xl whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {hasHighlight ? (
            <>
              {text.slice(0, highlightStart)}
              <mark
                ref={markRef}
                className="rounded-sm bg-amber-200/80 px-0.5 text-foreground"
              >
                {text.slice(highlightStart, end)}
              </mark>
              {text.slice(end)}
            </>
          ) : (
            text
          )}
        </div>
      </div>
    </div>
  );
}
