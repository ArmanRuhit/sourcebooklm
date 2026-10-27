"use client";

import { useEffect, useState } from "react";
import { ExternalLinkIcon } from "lucide-react";

import {
  getErrorMessage,
  getSourceContent,
  type Source,
  type SourceContent,
} from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; content: SourceContent };

export function TextSourceViewer({ source }: { source: Source }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    getSourceContent(source.id)
      .then((content) => {
        if (!cancelled) {
          setState({ status: "ready", content });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: "error", message: getErrorMessage(error) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [source.id]);

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
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <div className="mx-auto max-w-2xl whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {state.content.text ?? "No stored text for this source."}
        </div>
      </div>
    </div>
  );
}
