"use client";

import type { Citation } from "@/lib/api";

type CitationChipProps = {
  citation: Citation;
  onSelect: (citation: Citation) => void;
};

export function CitationChip({ citation, onSelect }: CitationChipProps) {
  return (
    <button
      type="button"
      title={citation.source_title}
      onClick={() => onSelect(citation)}
      className="mx-0.5 inline-flex translate-y-[-1px] items-center rounded-full bg-primary/10 px-1.5 py-0.5 align-baseline text-[10px] font-semibold text-primary transition-colors hover:bg-primary/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      [{citation.index}]
    </button>
  );
}
