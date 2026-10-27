"use client";

import { useEffect, useState } from "react";
import {
  BookOpenIcon,
  PlusIcon,
  RefreshCwIcon,
  TriangleAlertIcon,
} from "lucide-react";

import { AppHeader } from "@/components/app-header";
import { DeleteNotebookDialog } from "@/components/notebooks/delete-notebook-dialog";
import { NotebookCard } from "@/components/notebooks/notebook-card";
import { NotebookNameDialog } from "@/components/notebooks/notebook-name-dialog";
import { Button } from "@/components/ui/button";
import {
  createNotebook,
  getErrorMessage,
  listNotebooks,
  renameNotebook,
  type Notebook,
} from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; notebooks: Notebook[] };

export default function NotebooksPage() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [renaming, setRenaming] = useState<Notebook | null>(null);
  const [deleting, setDeleting] = useState<Notebook | null>(null);

  useEffect(() => {
    let cancelled = false;

    listNotebooks()
      .then((notebooks) => {
        if (!cancelled) {
          setState({ status: "ready", notebooks });
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
  }, [reloadKey]);

  function handleCreated(notebook: Notebook) {
    setState((current) =>
      current.status === "ready"
        ? { status: "ready", notebooks: [notebook, ...current.notebooks] }
        : current,
    );
  }

  function handleRenamed(notebook: Notebook) {
    setState((current) => {
      if (current.status !== "ready") {
        return current;
      }

      const notebooks = current.notebooks
        .map((item) => (item.id === notebook.id ? notebook : item))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

      return { status: "ready", notebooks };
    });
  }

  function handleDeleted(id: string) {
    setState((current) =>
      current.status === "ready"
        ? {
            status: "ready",
            notebooks: current.notebooks.filter((item) => item.id !== id),
          }
        : current,
    );
  }

  function retry() {
    setState({ status: "loading" });
    setReloadKey((key) => key + 1);
  }

  const notebooks = state.status === "ready" ? state.notebooks : [];

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon />
          New notebook
        </Button>
      </AppHeader>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-heading text-2xl font-semibold tracking-tight">
              Notebooks
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Workspaces for your sources and questions.
            </p>
          </div>
          {state.status === "ready" && notebooks.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {notebooks.length}{" "}
              {notebooks.length === 1 ? "notebook" : "notebooks"}
            </p>
          )}
        </div>

        {state.status === "loading" && (
          <div
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            aria-busy="true"
          >
            <span className="sr-only">Loading notebooks</span>
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className="h-32 animate-pulse rounded-xl border bg-muted/40"
              />
            ))}
          </div>
        )}

        {state.status === "error" && (
          <div
            role="alert"
            className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-6"
          >
            <div className="flex items-center gap-2 text-sm font-medium text-destructive">
              <TriangleAlertIcon className="size-4" />
              Could not load notebooks
            </div>
            <p className="text-sm text-muted-foreground">{state.message}</p>
            <Button variant="outline" onClick={retry}>
              <RefreshCwIcon />
              Try again
            </Button>
          </div>
        )}

        {state.status === "ready" && notebooks.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-20 text-center">
            <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-muted">
              <BookOpenIcon className="size-5 text-muted-foreground" />
            </div>
            <h2 className="font-heading text-lg font-medium">
              No notebooks yet
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Create a notebook to collect sources and ask questions grounded in
              them.
            </p>
            <Button className="mt-6" onClick={() => setCreateOpen(true)}>
              <PlusIcon />
              New notebook
            </Button>
          </div>
        )}

        {state.status === "ready" && notebooks.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {notebooks.map((notebook) => (
              <NotebookCard
                key={notebook.id}
                notebook={notebook}
                onRename={() => setRenaming(notebook)}
                onDelete={() => setDeleting(notebook)}
              />
            ))}
          </div>
        )}
      </main>

      {createOpen && (
        <NotebookNameDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setCreateOpen(false);
            }
          }}
          title="New notebook"
          description="Name the workspace. You can rename it later."
          submitLabel="Create notebook"
          onSubmit={async (name) => {
            handleCreated(await createNotebook(name));
          }}
        />
      )}

      {renaming && (
        <NotebookNameDialog
          key={renaming.id}
          open
          onOpenChange={(open) => {
            if (!open) {
              setRenaming(null);
            }
          }}
          title="Rename notebook"
          description="Give the workspace a new name."
          submitLabel="Save name"
          initialName={renaming.name}
          onSubmit={async (name) => {
            handleRenamed(await renameNotebook(renaming.id, name));
          }}
        />
      )}

      {deleting && (
        <DeleteNotebookDialog
          notebook={deleting}
          onOpenChange={(open) => {
            if (!open) {
              setDeleting(null);
            }
          }}
          onDeleted={handleDeleted}
        />
      )}
    </div>
  );
}
