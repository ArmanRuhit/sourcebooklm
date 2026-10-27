"use client";

import { useState } from "react";
import { ExternalLinkIcon, PlayIcon } from "lucide-react";

import { useSourceContent } from "@/hooks/use-source-content";
import type { Source } from "@/lib/api";
import { cn } from "cn";
import { formatTimestamp } from "@/lib/format";
import { readSegments } from "@/lib/segments";

export function YoutubeSourceViewer({
  source,
  initialStartSeconds = 0,
}: {
  source: Source;
  initialStartSeconds?: number;
}) {
  const state = useSourceContent(source.id);
  const [start, setStart] = useState(Math.max(0, initialStartSeconds));

  const videoId =
    typeof source.config.video_id === "string"
      ? source.config.video_id
      : null;
  const originalUrl =
    typeof source.config.url === "string" ? source.config.url : null;

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

  if (!videoId) {
    return (
      <p className="p-6 text-center text-sm text-destructive">
        This source is missing its YouTube video id.
      </p>
    );
  }

  const segments = readSegments(state.content.segments);
  const activeIndex = segments.reduce(
    (latest, segment, index) =>
      segment.startSeconds <= start ? index : latest,
    -1,
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="aspect-video w-full shrink-0 bg-black">
        <iframe
          key={start}
          src={`https://www.youtube.com/embed/${videoId}?start=${Math.floor(
            start,
          )}&autoplay=1`}
          title={source.title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="h-full w-full"
        />
      </div>

      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">
          {segments.length} transcript cues
        </span>
        {originalUrl && (
          <a
            href={originalUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Open on YouTube
            <ExternalLinkIcon className="size-3" />
          </a>
        )}
      </div>

      {segments.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-auto p-2">
          <ol className="flex flex-col gap-0.5">
            {segments.map((segment, index) => (
              <li key={`${segment.startSeconds}-${index}`}>
                <button
                  type="button"
                  onClick={() => setStart(segment.startSeconds)}
                  aria-current={index === activeIndex ? "true" : undefined}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted",
                    index === activeIndex && "bg-muted",
                  )}
                >
                  <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-[11px] tabular-nums text-muted-foreground">
                    <PlayIcon className="size-2.5" />
                    {formatTimestamp(segment.startSeconds)}
                  </span>
                  <span className="min-w-0">{segment.text}</span>
                </button>
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
