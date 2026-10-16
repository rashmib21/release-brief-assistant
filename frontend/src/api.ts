export class ApiError extends Error {
  status: number;
  detail: any;
  requestId: string | null;
  constructor(status: number, detail: unknown, requestId: string | null = null) {
    super(messageFrom(detail, status));
    this.status = status;
    this.detail = detail;
    this.requestId = requestId ?? (detail && typeof detail === "object" && "request_id" in detail ? String((detail as any).request_id) : null);
  }
  /** True when trying again later may work (server hiccup, AI provider busy, no connection). */
  get retryable(): boolean {
    return this.status === 0 || this.status >= 500 || this.status === 429 || this.detail?.retryable === true;
  }
}

// "body.package.features.0.text" -> "Completed features, item 1, text"
const FIELD_NAMES: Record<string, string> = {
  features: "Completed features",
  bug_fixes: "Bug fixes",
  changed_behaviour: "Changed behaviour",
  qa_summary: "QA summary",
  known_limitations: "Known limitations",
  migration_notes: "Migration notes",
  affected_user_groups: "Affected user groups",
  name: "Release name",
  edited_text: "Statement text",
};

function describeField(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  const parts = loc.filter((p) => p !== "body" && p !== "package");
  const name = FIELD_NAMES[String(parts[0])];
  if (!name) return parts.length ? String(parts[parts.length - 1]) : "";
  return typeof parts[1] === "number" ? `${name}, item ${parts[1] + 1}` : name;
}

export function messageFrom(detail: unknown, status = 0): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (!d || typeof d !== "object" || !("msg" in d)) return String(d);
        const field = describeField((d as any).loc);
        const msg = String((d as any).msg).replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as any).message);
  if (status === 429) return "Too many requests. Wait a minute and try again.";
  if (status >= 500) return "The server had a problem. Please try again in a moment.";
  return "Something went wrong. Please try again.";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body, res.headers.get("x-request-id"));
  return body as T;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/** Route params come from the URL, so they can be anything. Only positive whole numbers are real IDs. */
export const isValidId = (n: number) => Number.isInteger(n) && n > 0 && n < 2 ** 31;
