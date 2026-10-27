"use client";

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  CaptionsIcon,
  FileTextIcon,
  Link2Icon,
  Loader2Icon,
  TypeIcon,
  UploadIcon,
  VideoIcon,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { getErrorMessage } from "@/lib/api";
import { formatFileSize } from "@/lib/format";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

const SOURCE_TILES: {
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
  available: boolean;
}[] = [
  {
    key: "pdf",
    label: "PDF",
    description: "Papers, slides, reports",
    icon: FileTextIcon,
    available: true,
  },
  {
    key: "youtube",
    label: "YouTube",
    description: "Video transcripts",
    icon: VideoIcon,
    available: false,
  },
  {
    key: "url",
    label: "Web link",
    description: "Articles and docs",
    icon: Link2Icon,
    available: true,
  },
  {
    key: "text",
    label: "Text",
    description: "Paste notes directly",
    icon: TypeIcon,
    available: false,
  },
  {
    key: "vtt",
    label: "VTT",
    description: "Timestamped captions",
    icon: CaptionsIcon,
    available: false,
  },
];

type AddSourceDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (file: File) => Promise<void>;
  onAddUrl: (url: string) => Promise<void>;
};

export function AddSourceDialog({
  open,
  onOpenChange,
  onUpload,
  onAddUrl,
}: AddSourceDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"tiles" | "url">("tiles");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [addingUrl, setAddingUrl] = useState(false);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    event.target.value = "";

    if (!selected) {
      return;
    }

    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose a PDF file.");
      return;
    }

    if (selected.size > MAX_UPLOAD_BYTES) {
      setError("PDFs must be 20 MB or smaller.");
      return;
    }

    setError(null);
    setFile(selected);
  }

  async function handleUpload() {
    if (!file) {
      return;
    }

    setUploading(true);
    setError(null);

    try {
      await onUpload(file);
      onOpenChange(false);
    } catch (caught) {
      setError(getErrorMessage(caught));
      setUploading(false);
    }
  }

  async function handleUrlSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = url.trim();

    let parsed: URL;
    try {
      parsed = new URL(trimmed);
    } catch {
      setError("Enter a valid URL.");
      return;
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      setError("Use an http:// or https:// URL.");
      return;
    }

    setAddingUrl(true);
    setError(null);

    try {
      await onAddUrl(parsed.toString());
      onOpenChange(false);
    } catch (caught) {
      setError(getErrorMessage(caught));
      setAddingUrl(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a source</DialogTitle>
          <DialogDescription>
            Upload a PDF or add an article link. Other source types arrive in
            the next slices.
          </DialogDescription>
        </DialogHeader>

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={handleFileChange}
          tabIndex={-1}
        />

        {mode === "url" ? (
          <form onSubmit={handleUrlSubmit} className="grid gap-3" noValidate>
            <div className="grid gap-1.5">
              <label htmlFor="source-url" className="text-xs font-medium">
                Article URL
              </label>
              <Input
                id="source-url"
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/article"
                autoFocus
                disabled={addingUrl}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              We&apos;ll fetch the page, keep a text snapshot, and index it.
            </p>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setMode("tiles");
                  setError(null);
                }}
                disabled={addingUrl}
              >
                Back
              </Button>
              <Button type="submit" disabled={addingUrl || !url.trim()}>
                {addingUrl ? (
                  <Loader2Icon className="animate-spin" />
                ) : (
                  <Link2Icon />
                )}
                {addingUrl ? "Adding..." : "Add link"}
              </Button>
            </div>
          </form>
        ) : file ? (
          <div className="grid gap-3">
            <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-3">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-background">
                <FileTextIcon className="size-5 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatFileSize(file.size)}
                </p>
              </div>
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setFile(null);
                  setError(null);
                }}
                disabled={uploading}
              >
                Choose another
              </Button>
              <Button type="button" onClick={handleUpload} disabled={uploading}>
                {uploading ? (
                  <Loader2Icon className="animate-spin" />
                ) : (
                  <UploadIcon />
                )}
                {uploading ? "Uploading..." : "Upload PDF"}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              {SOURCE_TILES.map((tile) => {
                const Icon = tile.icon;

                return (
                  <button
                    key={tile.key}
                    type="button"
                    disabled={!tile.available}
                    onClick={() => {
                      if (tile.key === "pdf") {
                        inputRef.current?.click();
                      } else if (tile.key === "url") {
                        setMode("url");
                        setError(null);
                      }
                    }}
                    className="relative flex flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:bg-transparent"
                  >
                    <Icon className="size-5 text-muted-foreground" />
                    <span className="text-sm font-medium">{tile.label}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {tile.description}
                    </span>
                    {!tile.available && (
                      <span className="absolute top-2 right-2 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        Soon
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
