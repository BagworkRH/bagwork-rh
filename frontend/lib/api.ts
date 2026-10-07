/** API client for the Django REST backend (Spec 02 endpoints). */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ApiError(response.status, describeError(data));
  }

  return data as T;
}