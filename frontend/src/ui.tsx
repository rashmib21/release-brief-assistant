import { Component, createContext, useCallback, useContext, useEffect, useState, type ErrorInfo, type ReactNode } from "react";

import { ApiError } from "./api";
import type { StatementStatus } from "./types";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  const api = error instanceof ApiError ? error : null;
  // Offer Retry only when trying again can help. A 404 or a validation error will not fix itself.
  const canRetry = !!onRetry && (!api || api.retryable);
  return (
    <div className="alert alert-error" role="alert">
      <div>
        <div>{message}</div>
        {api?.requestId && api.status >= 500 && <div className="small muted">Reference: {api.requestId}</div>}
      </div>
      {canRetry && (
        <button className="btn" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Shows a friendly screen instead of a blank page if a component crashes while rendering. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("render error", error, info.componentStack);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="empty">
        <h3>This page hit a problem</h3>
        <p>Your saved work is safe. Reload the page, or go back to your releases.</p>
        <div className="row" style={{ justifyContent: "center" }}>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
          <a className="btn" href="/">
            Your releases
          </a>
        </div>
      </div>
    );
  }
}

const ANALYSIS_STAGES = [
  "Rating the impact of every change…",
  "Checking claims against the QA evidence…",
  "Drafting summaries for engineers and stakeholders…",
  "Still working. The AI provider can be slow at busy times…",
];

/** Shown while the three AI steps run (can take up to a minute). Elapsed time shows the page is not stuck. */
export function AnalysisProgress() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const stage = Math.min(Math.floor(seconds / 12), ANALYSIS_STAGES.length - 1);
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden /> {ANALYSIS_STAGES[stage]} <span className="muted small">({seconds}s)</span>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

const STATUS_LABEL: Record<StatementStatus, string> = { draft: "Draft", approved: "Approved", rejected: "Rejected", stale: "Stale" };
export const StatusBadge = ({ status }: { status: StatementStatus }) => <span className={`badge badge-${status}`}>{STATUS_LABEL[status]}</span>;
export const ImpactBadge = ({ impact }: { impact: string }) => <span className={`badge impact-${impact}`}>{impact}</span>;

// ---- toasts ----
type Toast = { id: number; msg: string; kind: "success" | "error" };
const ToastCtx = createContext<(msg: string, kind?: Toast["kind"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((msg: string, kind: Toast["kind"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
            {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
