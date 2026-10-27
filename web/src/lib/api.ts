import type { components } from "@/lib/api-types";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export type Notebook = components["schemas"]["NotebookRead"];
export type Source = components["schemas"]["SourceRead"];
export type SourceContent = components["schemas"]["SourceContentRead"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };

    if (typeof body.detail === "string") {
      return body.detail;
    }

    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: unknown } | undefined;
      if (typeof first?.msg === "string") {
        return first.msg;
      }
    }
  } catch {
    // Non-JSON error body — fall through to the status-based message.
  }

  return `Request failed (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData =
    typeof FormData !== "undefined" && init?.body instanceof FormData;

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !isFormData
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong.";
}

export function listNotebooks(): Promise<Notebook[]> {
  return request<Notebook[]>("/api/v1/notebooks", { cache: "no-store" });
}

export function getNotebook(id: string): Promise<Notebook> {
  return request<Notebook>(`/api/v1/notebooks/${id}`, { cache: "no-store" });
}

export function createNotebook(name: string): Promise<Notebook> {
  return request<Notebook>("/api/v1/notebooks", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function renameNotebook(id: string, name: string): Promise<Notebook> {
  return request<Notebook>(`/api/v1/notebooks/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteNotebook(id: string): Promise<void> {
  await request<void>(`/api/v1/notebooks/${id}`, { method: "DELETE" });
}

export function listSources(notebookId: string): Promise<Source[]> {
  return request<Source[]>(`/api/v1/notebooks/${notebookId}/sources`, {
    cache: "no-store",
  });
}

export function uploadPdf(notebookId: string, file: File): Promise<Source> {
  const body = new FormData();
  body.append("kind", "pdf");
  body.append("file", file);

  return request<Source>(`/api/v1/notebooks/${notebookId}/sources`, {
    method: "POST",
    body,
  });
}

export function uploadVtt(notebookId: string, file: File): Promise<Source> {
  const body = new FormData();
  body.append("kind", "vtt");
  body.append("file", file);

  return request<Source>(`/api/v1/notebooks/${notebookId}/sources`, {
    method: "POST",
    body,
  });
}

export function createUrlSource(notebookId: string, url: string): Promise<Source> {
  const body = new FormData();
  body.append("kind", "url");
  body.append("url", url);

  return request<Source>(`/api/v1/notebooks/${notebookId}/sources`, {
    method: "POST",
    body,
  });
}

export function createYoutubeSource(
  notebookId: string,
  url: string,
): Promise<Source> {
  const body = new FormData();
  body.append("kind", "youtube");
  body.append("url", url);

  return request<Source>(`/api/v1/notebooks/${notebookId}/sources`, {
    method: "POST",
    body,
  });
}

export function getSourceContent(sourceId: string): Promise<SourceContent> {
  return request<SourceContent>(`/api/v1/sources/${sourceId}/content`, {
    cache: "no-store",
  });
}

export function getSourceFileUrl(sourceId: string): string {
  return `${API_URL}/api/v1/sources/${sourceId}/file`;
}

export async function deleteSource(sourceId: string): Promise<void> {
  await request<void>(`/api/v1/sources/${sourceId}`, { method: "DELETE" });
}

export function reindexSource(sourceId: string): Promise<Source> {
  return request<Source>(`/api/v1/sources/${sourceId}/reindex`, {
    method: "POST",
  });
}
