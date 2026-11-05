/** API client for the Django REST backend (Spec 02 endpoints). */

/**
 * Where the API lives.
 *
 * The browser can only reach the public URL, so that is what it gets. A server
 * render is inside the compose network and must not go back out through nginx:
 * that hop spends the anonymous rate limit meant for visitors, and when it runs
 * dry the page behind the fetch fails. `INTERNAL_API_URL` is set by compose for
 * exactly that case, and everything else (local dev, a platform with no internal
 * network) falls back to the public URL.
 *
 * `process.env.INTERNAL_API_URL` is only ever evaluated on the server — the
 * browser takes the first branch — so the client bundle never touches it.
 */
export function apiBaseUrl(): string {
  const publicBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  if (typeof window !== "undefined") return publicBase;
  return process.env.INTERNAL_API_URL || publicBase;
}

const TOKEN_KEY = "bagwork_rh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

/** Turn a snake_case model field into words a person can read: `reward_rate` -> `Reward rate`. */
function humanizeField(field: string): string {
  const spaced = field.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Build a readable message from a DRF error body.
 *
 * The backend answers validation failures in two shapes: a flat
 * `{"detail": "..."}` for domain rules raised by the service, and a per-field
 * map like `{"reward_rate": ["A fixed reward per post must be greater than
 * zero."]}` for serializer field errors. The per-field shape is the common one
 * when creating a campaign, and collapsing it to "Request failed" would hide
 * exactly which field the brand must fix, so it is spelled out here.
 */
function describeError(data: unknown): string {
  if (typeof data === "string" && data) return data;
  if (Array.isArray(data)) return JSON.stringify(data);
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.detail === "string" && record.detail) return record.detail;
    const parts: string[] = [];
    for (const [field, value] of Object.entries(record)) {
      const text = Array.isArray(value) ? value.map(String).join(" ") : String(value);
      if (!text) continue;
      parts.push(field === "non_field_errors" ? text : `${humanizeField(field)}: ${text}`);
    }
    if (parts.length > 0) return parts.join(" · ");
  }
  return "Request failed";
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, auth = false } = options;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Token ${token}`;
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // A server render always wants live data: every page here shows current
    // figures. Next's default `force-cache` would both freeze them and make the
    // render depend on a writable Data Cache - which, in a container running as
    // an unprivileged user, is a dependency worth not having.
    ...(typeof window === "undefined" ? { cache: "no-store" as const } : {}),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ApiError(response.status, describeError(data));
  }

  return data as T;
}