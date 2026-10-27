import type { components } from "@/lib/api-types";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export type Notebook = components["schemas"]["NotebookRead"];

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
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
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
