"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  ArrowLeftIcon,
  RefreshCwIcon,
  SearchXIcon,
  XIcon,
} from "lucide-react";

import { AppHeader } from "@/components/app-header";
import { ChatPanel } from "@/components/chat/chat-panel";
import { AddSourceDialog } from "@/components/sources/add-source-dialog";
import { DeleteSourceDialog } from "@/components/sources/delete-source-dialog";
import { PdfViewerPanel } from "@/components/sources/pdf-viewer-panel";
import { SourceList } from "@/components/sources/source-list";
import { TextSourceViewer } from "@/components/sources/text-source-viewer";
import { VttSourceViewer } from "@/components/sources/vtt-source-viewer";
import { YoutubeSourceViewer } from "@/components/sources/youtube-source-viewer";
import { Button } from "@/components/ui/button";
import { useSources } from "@/hooks/use-sources";
import {
  ApiError,
  createUrlSource,
  createYoutubeSource,
  getErrorMessage,
  getNotebook,
  getSourceFileUrl,
  reindexSource,
  uploadPdf,
  uploadVtt,
  type Citation,
  type Notebook,
  type Source,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

type State =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error"; message: string }
  | { status: "ready"; notebook: Notebook };

export default function NotebookPage() {
  return (
    <Suspense fallback={<NotebookPageLoading />}>
      <NotebookPageContent />
    </Suspense>
  );
}

function NotebookPageLoading() {
  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
        <div className="mb-6 h-4 w-28 animate-pulse rounded bg-muted" />
        <div className="mb-8 h-7 w-56 animate-pulse rounded bg-muted" />
        <div className="grid flex-1 gap-4 lg:grid-cols-[320px_1fr]">
          <div className="h-72 animate-pulse rounded-xl border bg-muted/40" />
          <div className="h-72 animate-pulse rounded-xl border bg-muted/40" />
        </div>
        <span className="sr-only">Loading notebook</span>
      </main>
    </div>
  );
}

function NotebookPageContent() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<State>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getNotebook(id)
      .then((notebook) => {
        if (!cancelled) {
          setState({ status: "ready", notebook });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        if (
          error instanceof ApiError &&
          (error.status === 404 || error.status === 422)
        ) {
          // 422 here means the id is not a valid UUID, which is just another
          // way of asking for a notebook that cannot exist.
          setState({ status: "missing" });
          return;
        }

        setState({ status: "error", message: getErrorMessage(error) });
      });

    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  if (state.status === "loading") {
    return <NotebookPageLoading />;
  }

  if (state.status === "missing") {
    return (
      <div className="flex min-h-screen flex-col">
        <AppHeader />
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center gap-4 px-4 py-20 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted">
            <SearchXIcon className="size-5 text-muted-foreground" />
          </div>
          <h1 className="font-heading text-xl font-medium">
            Notebook not found
          </h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            It may have been deleted, or the link is wrong.
          </p>
          <Button
            render={<Link href="/notebooks" />}
            nativeButton={false}
            variant="outline"
          >
            <ArrowLeftIcon />
            Back to notebooks
          </Button>
        </main>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex min-h-screen flex-col">
        <AppHeader />
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center gap-4 px-4 py-20 text-center">
          <h1 className="font-heading text-xl font-medium">
            Could not load this notebook
          </h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            {state.message}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setState({ status: "loading" });
                setReloadKey((key) => key + 1);
              }}
            >
              <RefreshCwIcon />
              Try again
            </Button>
            <Button
              render={<Link href="/notebooks" />}
              nativeButton={false}
              variant="ghost"
            >
              <ArrowLeftIcon />
              All notebooks
            </Button>
          </div>
        </main>
      </div>
    );
  }

  const { notebook } = state;

  return <NotebookWorkspace notebook={notebook} />;
}

function NotebookWorkspace({ notebook }: { notebook: Notebook }) {
  const {
    sources,
    error: sourcesError,
    reload,
    addSource,
    updateSource,
    removeSource,
  } = useSources(notebook.id);
  const [addOpen, setAddOpen] = useState(false);
  const [deletingSource, setDeletingSource] = useState<Source | null>(null);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<{
    source: Source;
    page: number;
    startSeconds: number;
    citation: Citation | null;
  } | null>(null);

  const readySourceCount =
    sources?.filter((source) => source.status === "ready").length ?? 0;

  async function handleUpload(file: File) {
    const source = await uploadPdf(notebook.id, file);
    addSource(source);
  }

  async function handleUploadVtt(file: File) {
    const source = await uploadVtt(notebook.id, file);
    addSource(source);
  }

  async function handleAddUrl(url: string) {
    const source = await createUrlSource(notebook.id, url);
    addSource(source);
  }

  async function handleAddYoutube(url: string) {
    const source = await createYoutubeSource(notebook.id, url);
    addSource(source);
  }

  async function handleReindex(source: Source) {
    setBusySourceId(source.id);
    setActionError(null);

    try {
      const updated = await reindexSource(source.id);
      updateSource(updated);
    } catch (caught) {
      setActionError(getErrorMessage(caught));
    } finally {
      setBusySourceId(null);
    }
  }

  function handleDeleted(id: string) {
    removeSource(id);
    setViewer((current) => (current?.source.id === id ? null : current));
    setActionError(null);
  }

  function handleCitation(citation: Citation) {
    const source = sources?.find((item) => item.id === citation.source_id);

    if (!source) {
      setActionError("That cited source is no longer available.");
      return;
    }

    setViewer({
      source,
      page: citation.page ?? 1,
      startSeconds: citation.start_seconds ?? 0,
      citation,
    });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-col gap-1">
          <Link
            href="/notebooks"
            className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" />
            All notebooks
          </Link>
          <h1 className="truncate font-heading text-xl font-semibold tracking-tight">
            {notebook.name}
          </h1>
          <p className="text-xs text-muted-foreground">
            Created {formatRelativeTime(notebook.created_at)}
          </p>
        </div>

        <div
          className={`grid flex-1 gap-4 lg:grid-cols-[320px_1fr] ${
            viewer
              ? "xl:grid-cols-[300px_minmax(0,1fr)_minmax(360px,1fr)]"
              : ""
          }`}
        >
          <SourceList
            sources={sources}
            error={sourcesError}
            actionError={actionError}
            busySourceId={busySourceId}
            activeSourceId={viewer?.source.id}
            onAdd={() => setAddOpen(true)}
            onRetry={reload}
            onOpen={(source) =>
              setViewer({
                source,
                page: 1,
                startSeconds: 0,
                citation: null,
              })
            }
            onReindex={handleReindex}
            onDelete={setDeletingSource}
          />

          <ChatPanel
            notebookId={notebook.id}
            readySourceCount={readySourceCount}
            onCitation={handleCitation}
          />

          {viewer && (
            <section className="flex min-h-96 flex-col rounded-xl border bg-card">
              <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
                <h2 className="truncate text-sm font-medium">
                  {viewer.source.title}
                </h2>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label="Close viewer"
                  onClick={() => setViewer(null)}
                >
                  <XIcon />
                </Button>
              </div>
              {viewer.source.kind === "pdf" ? (
                <PdfViewerPanel
                  key={viewer.source.id}
                  url={getSourceFileUrl(viewer.source.id)}
                  initialPage={viewer.page}
                  snippet={viewer.citation?.snippet}
                />
              ) : viewer.source.kind === "youtube" ? (
                <YoutubeSourceViewer
                  key={viewer.source.id}
                  source={viewer.source}
                  initialStartSeconds={viewer.startSeconds}
                />
              ) : viewer.source.kind === "vtt" ? (
                <VttSourceViewer
                  key={viewer.source.id}
                  source={viewer.source}
                  highlightStart={viewer.citation?.start_seconds}
                  highlightEnd={viewer.citation?.end_seconds}
                />
              ) : (
                <TextSourceViewer
                  key={viewer.source.id}
                  source={viewer.source}
                  highlightStart={viewer.citation?.char_start}
                  highlightEnd={viewer.citation?.char_end}
                  snippet={viewer.citation?.snippet}
                />
              )}
            </section>
          )}
        </div>
      </main>

      {addOpen && (
        <AddSourceDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          onUpload={handleUpload}
          onUploadVtt={handleUploadVtt}
          onAddUrl={handleAddUrl}
          onAddYoutube={handleAddYoutube}
        />
      )}

      {deletingSource && (
        <DeleteSourceDialog
          source={deletingSource}
          onOpenChange={(open) => {
            if (!open) {
              setDeletingSource(null);
            }
          }}
          onDeleted={handleDeleted}
        />
      )}
    </div>
  );
}
