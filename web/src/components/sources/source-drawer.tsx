"use client";

import type { ReactNode } from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

type SourceDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
};

export function SourceDrawer({ open, onOpenChange, children }: SourceDrawerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-0 left-0 flex h-dvh max-h-dvh w-80 max-w-[85vw] translate-x-0 translate-y-0 flex-col content-start gap-0 overflow-hidden rounded-none p-0 sm:max-w-xs"
      >
        <DialogTitle className="border-b px-4 py-3 pr-12 text-sm">Sources</DialogTitle>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
