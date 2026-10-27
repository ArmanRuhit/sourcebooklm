import { cn } from "cn";

import type { Source } from "@/lib/api";

const STAGE_LABELS = {
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  indexing: "Indexing",
} as const;

const STATUS_CLASSES: Record<Source["status"], { label: string; dot: string }> = {
  queued: { label: "Queued", dot: "bg-amber-400" },
  processing: { label: "Indexing", dot: "bg-amber-500 animate-pulse" },
  ready: { label: "Ready", dot: "bg-emerald-500" },
  failed: { label: "Failed", dot: "bg-destructive" },
};

export function SourceStatusChip({ source }: { source: Source }) {
  const status = STATUS_CLASSES[source.status];
  const label =
    source.status === "processing" && source.stage
      ? STAGE_LABELS[source.stage]
      : status.label;

  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] text-muted-foreground">
      <span className={cn("size-2 rounded-full", status.dot)} aria-hidden="true" />
      {label}
    </span>
  );
}
