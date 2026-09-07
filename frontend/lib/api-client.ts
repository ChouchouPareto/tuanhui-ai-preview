const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type AppError = Error & { code?: string; retryable?: boolean; requestId?: string };

async function readBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return null;
  return response.json();
}

function getErrorMessage(body: unknown): string {
  if (!body || typeof body !== "object") return "请求失败，请稍后重试";
  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (record.detail && typeof record.detail === "object" && "message" in record.detail) return String(record.detail.message);
  if (record.error && typeof record.error === "object") {
    const message = (record.error as Record<string, unknown>).message;
    if (typeof message === "string") return message;
  }
  return "请求失败，请稍后重试";
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const body = await readBody(response);
  if (!response.ok) {
    const error = new Error(getErrorMessage(body)) as AppError;
    error.code = `HTTP_${response.status}`;
    error.retryable = response.status >= 500 || response.status === 429;
    error.requestId = response.headers.get("x-request-id") ?? undefined;
    throw error;
  }
  return body as T;
}

export function jsonRequest(method: "POST" | "PATCH", body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}
