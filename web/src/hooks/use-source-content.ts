"use client";

import { useEffect, useState } from "react";

import {
  getErrorMessage,
  getSourceContent,
  type SourceContent,
} from "@/lib/api";

export type SourceContentState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; content: SourceContent };

export function useSourceContent(sourceId: string): SourceContentState {
  const [state, setState] = useState<SourceContentState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    getSourceContent(sourceId)
      .then((content) => {
        if (!cancelled) {
          setState({ status: "ready", content });
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
  }, [sourceId]);

  return state;
}
