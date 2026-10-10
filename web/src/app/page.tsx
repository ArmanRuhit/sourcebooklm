"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Health = 
  | { status: "checking"}
  | { status: "ok"; payload: { status: string} }
  | { status: "error"; message: string }


export default function Home() {
  const [health, setHealth] = useState<Health>({ status: "checking"});

  useEffect(() => {
    let cancelled = false;

    async function check(){
      try {
        const response = await fetch(`${API_URL}/api/v1/health`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const payload = (await response.json()) as { status: string };
        if (!cancelled) {
          setHealth({ status: "ok", payload });
        }
      } catch (error) {
        if (!cancelled) {
          setHealth({ status: "error", message: error instanceof Error ? error.message : "unknown error" });
        }
      }
    }

    check();

    return () => {
      cancelled = true;
    }
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">SourcebookLM</h1>
        <p className="text-sm text-muted-foreground">
          Grounded answers from your own sources.
        </p>
      </div>


      <section className="w-full max-w-sm rounded-lg border bg-card p-4 text-center">
        <h2 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            API health
        </h2>
        {health.status === "checking" && <p className="text-sm">Checking...</p>}
        {health.status === "ok" && (
          <p className="text-sm font-medium text-green-600 dark:text-green-400">
            API: {health.payload.status}
          </p>
        )}
        {health.status === "error" && (
          <p className="text-sm font-medium text-red-600 dark:text-red-400">
            Unreachable: {health.message}
          </p>
        )}
      </section>

    </main>
  )
}