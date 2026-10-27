"use client";

import { useCallback, useEffect, useState } from "react";

import { getErrorMessage, listSources, type Source } from "@/lib/api";

type UseSourcesResult = {
  sources: Source[] | null;
  error: string | null;
  reload: () => void;
  addSource: (source: Source) => void;
  updateSource: (source: Source) => void;
  removeSource: (sourceId: string) => void;
};

/**
 * Load a notebook's sources, then poll every 2s while any are still being
 * ingested. Polling stops as soon as everything is ready or failed.
 */
export function useSources(notebookId: string): UseSourcesResult {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const next = await listSources(notebookId);
        if (cancelled) {
          return;
        }

        setSources(next);
        setError(null);

        if (next.some((source) => source.status === "queued" || source.status === "processing")) {
          timer = setTimeout(() => void poll(), 2000);
        }
      } catch (caught) {
        if (cancelled) {
          return;
        }

        setError(getErrorMessage(caught));
        timer = setTimeout(() => void poll(), 4000);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [notebookId, reloadKey]);

  const addSource = useCallback((source: Source) => {
    setSources((current) => (current ? [source, ...current] : [source]));
    // Restart the polling effect: the previous chain stopped once the old
    // list was fully settled, before this new queued source existed.
    setReloadKey((key) => key + 1);
  }, []);

  const updateSource = useCallback((source: Source) => {
    setSources((current) =>
      current
        ? current.map((item) => (item.id === source.id ? source : item))
        : current,
    );
    setReloadKey((key) => key + 1);
  }, []);

  const removeSource = useCallback((sourceId: string) => {
    setSources((current) =>
      current ? current.filter((source) => source.id !== sourceId) : current,
    );
  }, []);

  return { sources, error, reload, addSource, updateSource, removeSource };
}
