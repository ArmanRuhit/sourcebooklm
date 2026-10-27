"use client";

import {
  CaptionsIcon,
  FileStackIcon,
  FileTextIcon,
  Link2Icon,
  PlusIcon,
  RefreshCwIcon,
  VideoIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { SourceStatusChip } from "@/components/sources/source-status-chip";
import type { Source } from "@/lib/api";
import { formatFileSize } from "@/lib/format";

type SourceListProps = {
  sources: Source[] | null;
  error: string | null;
  activeSourceId?: string;
  onAdd: () => void;
  onRetry: () => void;
  onOpen: (source: Source) => void;
};

function sourceMeta(source: Source): string {
  let kindLabel: string;

  if (source.kind === "pdf") {
    kindLabel =
      typeof source.config.size_bytes === "number"
        ? formatFileSize(source.config.size_bytes)
        : "PDF";
  } else if (source.kind === "url") {
    kindLabel = "Web";
    if (typeof source.config.url === "string") {
      try {
        kindLabel = new URL(source.config.url).hostname.replace(/^www\./, "");
      } catch {
        // Keep the generic label for a malformed stored URL.
      }
    }
  } else if (source.kind === "youtube") {
    kindLabel = "YouTube";
  } else if (source.kind === "vtt") {
    kindLabel = "VTT";
  } else {
    kindLabel = "Text";
  }

  if (source.status === "ready") {
    const chunks = source.chunk_count ?? 0;
    return `${chunks} ${chunks === 1 ? "chunk" : "chunks"} · ${kindLabel}`;
  }

  if (source.status === "failed") {
    return `${kindLabel} · ingestion failed`;
  }

  if (source.status === "processing") {
    return kindLabel;
  }

  return `${kindLabel} · waiting for worker`;
}

export function SourceList({
  sources,
  error,
  activeSourceId,
  onAdd,
  onRetry,
  onOpen,
}: SourceListProps) {
  return (
    <aside className="flex min-h-72 flex-col rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          Sources
          {sources && sources.length > 0 && (
            <span className="text-xs font-normal text-muted-foreground">
              {sources.length}
            </span>
          )}
        </h2>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <PlusIcon />
          Add
        </Button>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-2 border-b bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <span className="min-w-0 truncate">{error}</span>
          <Button size="xs" variant="ghost" onClick={onRetry}>
            <RefreshCwIcon />
            Retry
          </Button>
        </div>
      )}

      {sources === null ? (
        <div className="grid gap-2 p-3">
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              className="h-14 animate-pulse rounded-lg bg-muted/60"
            />
          ))}
        </div>
      ) : sources.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
          <div className="flex size-11 items-center justify-center rounded-full bg-muted">
            <FileStackIcon className="size-5 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">No sources yet</p>
          <p className="max-w-56 text-xs text-muted-foreground">
            Upload a PDF or VTT, add an article, or paste a YouTube URL.
          </p>
          <Button size="sm" variant="outline" className="mt-2" onClick={onAdd}>
            <PlusIcon />
            Add a source
          </Button>
        </div>
      ) : (
        <ul className="flex flex-col gap-1 p-2">
          {sources.map((source) => {
            const canOpen = source.status === "ready";
            const active = activeSourceId === source.id;

            return (
              <li key={source.id}>
                <button
                  type="button"
                  onClick={() => {
                    if (canOpen) {
                      onOpen(source);
                    }
                  }}
                  aria-disabled={!canOpen}
                  aria-current={active ? "true" : undefined}
                  className="flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:cursor-default aria-disabled:hover:bg-transparent data-[active=true]:bg-muted"
                  data-active={active}
                >
                  <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border bg-background">
                    {source.kind === "url" ? (
                      <Link2Icon className="size-4 text-muted-foreground" />
                    ) : source.kind === "youtube" ? (
                      <VideoIcon className="size-4 text-muted-foreground" />
                    ) : source.kind === "vtt" ? (
                      <CaptionsIcon className="size-4 text-muted-foreground" />
                    ) : (
                      <FileTextIcon className="size-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">
                        {source.title}
                      </span>
                      <SourceStatusChip source={source} />
                    </div>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {sourceMeta(source)}
                    </p>
                    {source.status === "failed" && source.error && (
                      <p className="mt-1 line-clamp-2 text-[11px] text-destructive">
                        {source.error}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
