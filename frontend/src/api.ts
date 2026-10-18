/** Minimal typed fetch client for the NOESIS backend. */

const TOKEN_KEY = "noesis_token";
const USER_KEY = "noesis_user";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): { id: string; email: string; tenant_id: string; role: string } | null {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function setSession(token: string, user: unknown): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 401) {
    clearSession();
    window.location.hash = "#/login";
  }
  const text = await resp.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!resp.ok) {
    const err = body as { message?: string; detail?: unknown; error?: string };
    throw new ApiError(
      resp.status,
      err?.message ?? (typeof err?.detail === "string" ? err.detail : `HTTP ${resp.status}`),
      err?.detail ?? body,
    );
  }
  return body as T;
}

export function downloadArtifact(artifactId: string, filename: string): void {
  fetch(`/api/artifacts/${artifactId}/download`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
    .then((r) => r.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
}

export function artifactUrl(artifactId: string): string {
  return `/api/artifacts/${artifactId}/download`;
}

/** Subscribe to job SSE events; returns a cleanup function. */
export function subscribeJobEvents(
  jobId: string,
  onEvent: (evt: Record<string, unknown>) => void,
): () => void {
  const es = new EventSource(
    `/api/jobs/${jobId}/events?access_token=${getToken() ?? ""}`,
  );
  // EventSource cannot set headers: the backend also accepts query token via
  // bearer only, so we pass token as Authorization using fetch-stream instead.
  es.close();

  const ctrl = new AbortController();
  void (async () => {
    try {
      const resp = await fetch(`/api/jobs/${jobId}/events`, {
        headers: {
          Authorization: `Bearer ${getToken() ?? ""}`,
          Accept: "text/event-stream",
        },
        signal: ctrl.signal,
      });
      if (!resp.ok || !resp.body) return;
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (line) {
            try {
              onEvent(JSON.parse(line.slice(6)));
            } catch {
              /* ignore malformed frame */
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") console.warn("SSE stream ended", err);
    }
  })();

  return () => ctrl.abort();
}