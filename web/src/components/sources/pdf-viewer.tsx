"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { Button } from "@/components/ui/button";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export type PdfViewerProps = {
  url: string;
  initialPage?: number;
  snippet?: string | null;
};

function compactWithOffsets(text: string): { compact: string; offsets: number[] } {
  let compact = "";
  const offsets: number[] = [];

  for (let index = 0; index < text.length; index += 1) {
    if (!/\s/.test(text[index])) {
      compact += text[index];
      offsets.push(index);
    }
  }

  return { compact, offsets };
}

function highlightCitation(root: HTMLElement | null, snippet: string | null) {
  if (!root || !snippet) {
    return;
  }

  const layer = root.querySelector<HTMLElement>(".react-pdf__Page__textContent");
  const registry = (
    CSS as unknown as {
      highlights?: { set: (name: string, value: unknown) => void };
    }
  ).highlights;
  const HighlightConstructor = (
    window as unknown as { Highlight?: new (...ranges: Range[]) => unknown }
  ).Highlight;

  if (!layer || !registry || !HighlightConstructor) {
    return;
  }

  const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; start: number; end: number }[] = [];
  let text = "";
  let current = walker.nextNode();

  while (current) {
    const node = current as Text;
    nodes.push({ node, start: text.length, end: text.length + node.data.length });
    text += node.data;
    current = walker.nextNode();
  }

  const page = compactWithOffsets(text);
  const needle = compactWithOffsets(snippet).compact.slice(0, 40);
  if (!needle) {
    return;
  }

  const match = page.compact.indexOf(needle);
  if (match < 0) {
    return;
  }

  const rawStart = page.offsets[match];
  const rawEnd = page.offsets[match + needle.length - 1] + 1;
  const start = nodes.find((item) => rawStart >= item.start && rawStart < item.end);
  const end = nodes.find((item) => rawEnd > item.start && rawEnd <= item.end);

  if (!start || !end) {
    return;
  }

  const range = document.createRange();
  range.setStart(start.node, rawStart - start.start);
  range.setEnd(end.node, rawEnd - end.start);
  registry.set("sourcebooklm-citation", new HighlightConstructor(range));
}

export function PdfViewer({ url, initialPage = 1, snippet = null }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [page, setPage] = useState(initialPage);

  useEffect(() => {
    const element = containerRef.current;

    if (!element) {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setContainerWidth(Math.floor(entry.contentRect.width));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const pageWidth = containerWidth > 0 ? Math.min(containerWidth - 32, 680) : 0;

  useEffect(() => {
    if (!snippet) {
      return;
    }

    let cancelled = false;
    let attempts = 0;

    function apply() {
      if (cancelled) {
        return;
      }
      highlightCitation(pageRef.current, snippet);
      attempts += 1;
      if (attempts < 20) {
        requestAnimationFrame(apply);
      }
    }

    apply();
    return () => {
      cancelled = true;
    };
  }, [page, snippet, numPages]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <style>{`::highlight(sourcebooklm-citation) { background-color: #fde68a; color: #422006; }`}</style>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">PDF preview</span>
        <div className="flex items-center gap-1">
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Previous page"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={page <= 1}
          >
            <ChevronLeftIcon />
          </Button>
          <span className="min-w-24 text-center text-xs tabular-nums text-muted-foreground">
            {numPages ? `Page ${page} of ${numPages}` : "Loading..."}
          </span>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Next page"
            onClick={() =>
              setPage((current) => Math.min(numPages ?? current, current + 1))
            }
            disabled={numPages === null || page >= numPages}
          >
            <ChevronRightIcon />
          </Button>
        </div>
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

      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto bg-muted/40 p-4">
        <Document
          file={url}
          onLoadSuccess={(pdf) => {
            setNumPages(pdf.numPages);
            setPage((current) => Math.min(current, pdf.numPages));
          }}
          loading={<p className="py-10 text-center text-sm text-muted-foreground">Loading PDF...</p>}
          error={
            <p className="py-10 text-center text-sm text-destructive">
              Could not render this PDF.
            </p>
          }
          className="flex flex-col items-center gap-3"
        >
          {pageWidth > 0 && (
            <div ref={pageRef}>
              <Page
                pageNumber={page}
                width={pageWidth}
                onRenderTextLayerSuccess={() =>
                  highlightCitation(pageRef.current, snippet)
                }
                className="overflow-hidden rounded-sm shadow-sm ring-1 ring-foreground/10"
              />
            </div>
          )}
        </Document>
      </div>
    </div>
  );
}
