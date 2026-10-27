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

export function PdfViewer({ url, initialPage = 1, snippet = null }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
            <Page
              pageNumber={page}
              width={pageWidth}
              className="overflow-hidden rounded-sm shadow-sm ring-1 ring-foreground/10"
            />
          )}
        </Document>
      </div>
    </div>
  );
}
