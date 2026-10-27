"use client";

import dynamic from "next/dynamic";

import type { PdfViewerProps } from "@/components/sources/pdf-viewer";

const PdfViewer = dynamic<PdfViewerProps>(
  () => import("@/components/sources/pdf-viewer").then((module) => module.PdfViewer),
  {
    ssr: false,
    loading: () => (
      <p className="p-6 text-center text-sm text-muted-foreground">
        Loading viewer...
      </p>
    ),
  },
);

export function PdfViewerPanel(props: PdfViewerProps) {
  return <PdfViewer {...props} />;
}
