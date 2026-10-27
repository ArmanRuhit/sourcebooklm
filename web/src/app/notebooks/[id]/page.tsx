"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  ArrowLeftIcon,
  FileStackIcon,
  MessageSquareIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchXIcon,
  SendIcon,
} from "lucide-react";

import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  getErrorMessage,
  getNotebook,
  type Notebook,
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

        <div className="grid flex-1 gap-4 lg:grid-cols-[320px_1fr]">
          <aside className="flex min-h-72 flex-col rounded-xl border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="text-sm font-medium">Sources</h2>
              <Button size="sm" variant="outline" disabled>
                <PlusIcon />
                Add
              </Button>
            </div>
            <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
              <div className="flex size-11 items-center justify-center rounded-full bg-muted">
                <FileStackIcon className="size-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">No sources yet</p>
              <p className="max-w-56 text-xs text-muted-foreground">
                PDFs, web pages, YouTube videos, text, and VTT transcripts land
                here in Phase 2.
              </p>
            </div>
          </aside>

          <section className="flex min-h-96 flex-col rounded-xl border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="text-sm font-medium">Chat</h2>
              <span className="text-xs text-muted-foreground">0 messages</span>
            </div>
            <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-12 text-center">
              <div className="flex size-11 items-center justify-center rounded-full bg-muted">
                <MessageSquareIcon className="size-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">Grounded answers will appear here</p>
              <p className="max-w-sm text-xs text-muted-foreground">
                Add a source, then ask a question. Every answer will cite the
                exact passage it came from.
              </p>
            </div>
            <div className="border-t p-4">
              <div className="flex items-center gap-2 rounded-lg border bg-muted/30 py-1.5 pr-1.5 pl-3">
                <span className="flex-1 truncate text-sm text-muted-foreground">
                  Ask a question about your sources...
                </span>
                <Button size="sm" disabled>
                  <SendIcon />
                  Send
                </Button>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
