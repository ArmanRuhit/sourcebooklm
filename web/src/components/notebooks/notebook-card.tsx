"use client";

import { PencilIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Notebook } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

type NotebookCardProps = {
  notebook: Notebook;
  onRename: () => void;
  onDelete: () => void;
};

export function NotebookCard({
  notebook,
  onRename,
  onDelete,
}: NotebookCardProps) {
  return (
    <article className="group flex min-h-32 flex-col justify-between gap-6 rounded-xl border bg-card p-5 transition-colors hover:border-foreground/25">
      <div className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 truncate font-heading text-base font-medium tracking-tight">
          {notebook.name}
        </h2>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Rename ${notebook.name}`}
            onClick={onRename}
          >
            <PencilIcon />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete ${notebook.name}`}
            onClick={onDelete}
          >
            <Trash2Icon className="text-destructive" />
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Updated {formatRelativeTime(notebook.updated_at)}
      </p>
    </article>
  );
}
