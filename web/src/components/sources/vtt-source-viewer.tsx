"use client";

import { useEffect, useRef } from "react";
import { CaptionsIcon, ExternalLinkIcon } from "lucide-react";

import { useSourceContent } from "@/hooks/use-source-content";
import { getSourceFileUrl, type Source } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { readSegments } from "@/lib/segments";

type VttSourceViewerProps = {
  source: Source;
  highlightStart?: number | null;
  highlightEnd?: number | null;
};

export function VttSourceViewer({
  source,
  highlightStart = null,
  highlightEnd = null,
}: VttSourceViewerProps) {
  const state = useSourceContent(source.id);
  const containerRef = useRef<HTMLDivElement>(null);

  const segments =
    state.status === "ready" ? readSegments(state.content.segments) : [];

  const activeIndex =
    highlightStart === null || highlightEnd === null
      ? -1
      : segments.findIndex(
          (segment) =>
            segment.endSeconds >= highlightStart &&
            segment.startSeconds <= highlightEnd,
        );

  useEffect(() => {
    if (state.status === "ready" && activeIndex >= 0) {
      containerRef.current
        ?.querySelector('[data-active="true"]')
        ?.scrollIntoView({ block: "center" });
    }
  }, [state.status, activeIndex]);

  if (state.status === "loading") {
    return (
      <p className="p-6 text-center text-sm text-muted-foreground">
        Loading transcript...
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">
          {segments.length > 0
            ? `${segments.length} transcript ${segments.length === 1 ? "cue" : "cues"}`
            : `${source.char_count ?? 0} characters`}
        </span>
        <a
          href={getSourceFileUrl(source.id)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Open original
          <ExternalLinkIcon className="size-3" />
        </a>
      </div>

      {segments.length > 0 ? (
        <div ref={containerRef} className="min-h-0 flex-1 overflow-auto p-2">
          <ol className="flex flex-col gap-0.5">
            {segments.map((segment, index) => (
              <li
                key={`${segment.startSeconds}-${index}`}
                data-active={index === activeIndex}
                className="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm data-[active=true]:bg-amber-100/80"
              >
                <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-[11px] tabular-nums text-muted-foreground">
                  <CaptionsIcon className="size-2.5" />
                  {formatTimestamp(segment.startSeconds)}
                </span>
                <span className="min-w-0">{segment.text}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto p-4">
          <div className="mx-auto max-w-2xl whitespace-pre-wrap text-sm leading-relaxed">
            {state.content.text ?? "No stored transcript for this source."}
          </div>
        </div>
      )}
    </div>
  );
}
