import { useState } from "react";

import type { Statement } from "../types";
import { StatusBadge } from "../ui";

type Patch = { edited_text?: string; citations?: string[]; status?: string };

type Props = {
  s: Statement;
  locked: boolean;
  entering?: boolean;
  selectedCite: string | null; // the evidence chip currently open for this statement
  onSelectCite: (citeId: string | null) => void;
  onPatch: (id: number, body: Patch) => Promise<unknown>;
};

export default function StatementCard({ s, locked, entering, selectedCite, onSelectCite, onPatch }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(s.effective_text);
  const [cites, setCites] = useState(s.citations.map((c) => c.id).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const citeIds = s.citations.map((c) => c.id).join(", ");

  async function run(body: Patch) {
    setBusy(true);
    setError(null);
    try {
      await onPatch(s.id, body);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "The change was not saved. Try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    const body: Patch = {};
    if (text.trim() !== s.effective_text) body.edited_text = text;
    const ids = cites.split(/[\s,]+/).filter(Boolean).map((c) => c.toUpperCase());
    if (ids.join() !== s.citations.map((c) => c.id).join()) body.citations = ids;
    if (!Object.keys(body).length) return setEditing(false);
    if (await run(body)) setEditing(false);
  }

  function startEdit() {
    setText(s.effective_text);
    setCites(citeIds);
    setError(null);
    setEditing(true);
  }

  const open = s.citations.find((c) => c.id === selectedCite);

  return (
    <article className={`claim claim-${s.status} ${entering ? "claim-enter" : ""}`} aria-label={`${s.audience} ${s.section} statement, ${s.status}`}>
      <div className="claim-head">
        <StatusBadge status={s.status} />
        {s.edited_text && <span className="muted small">Edited by you</span>}
      </div>

      {s.status === "stale" && s.stale_reason && (
        <div className="alert alert-warn">
          <span>
            <strong>Out of date:</strong> {s.stale_reason}. Check the wording against the new package, then edit and approve it, or reject it.
          </span>
        </div>
      )}
      {s.flags.map((f) => (
        <div key={f.code} className="alert alert-error">
          <span>{f.message}</span>
        </div>
      ))}

      {editing ? (
        <div>
          <label htmlFor={`edit-${s.id}`}>Statement</label>
          <textarea id={`edit-${s.id}`} rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
          <label htmlFor={`cites-${s.id}`}>Evidence item IDs, separated by commas</label>
          <input id={`cites-${s.id}`} value={cites} onChange={(e) => setCites(e.target.value)} />
        </div>
      ) : (
        <p className="claim-text">{s.effective_text}</p>
      )}

      <div className="claim-meta">
        <span className="lbl">Evidence</span>
        {s.citations.map((c) => (
          <button key={c.id} type="button" className={`chip ${c.exists ? "" : "chip-missing"}`} aria-expanded={selectedCite === c.id} onClick={() => onSelectCite(selectedCite === c.id ? null : c.id)}>
            {c.id}
            {!c.exists && " (removed)"}
          </button>
        ))}
      </div>
      {open && <blockquote className="cite-inline">{open.exists ? open.item_text : `${open.id} is no longer in the package.`}</blockquote>}

      {error && (
        <div className="alert alert-error" role="alert">
          <span>{error}</span>
        </div>
      )}

      {!locked && (
        <div className="claim-actions">
          {editing ? (
            <>
              <button className="btn btn-small btn-primary" disabled={busy} onClick={saveEdit}>
                {busy ? "Saving…" : "Save changes"}
              </button>
              <button className="btn btn-small" disabled={busy} onClick={() => { setEditing(false); setError(null); }}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-small btn-approve" disabled={busy || s.status === "approved"} onClick={() => run({ status: "approved" })}>
                Approve
              </button>
              <button className="btn btn-small btn-reject" disabled={busy || s.status === "rejected"} onClick={() => run({ status: "rejected" })}>
                Reject
              </button>
              <button className="btn btn-small" disabled={busy} onClick={startEdit}>
                Edit
              </button>
              {(s.status === "approved" || s.status === "rejected") && (
                <button className="btn btn-small" disabled={busy} onClick={() => run({ status: "draft" })}>
                  Undo
                </button>
              )}
            </>
          )}
        </div>
      )}
    </article>
  );
}
