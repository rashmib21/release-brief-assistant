import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, isValidId } from "../api";
import type { ReleaseDetail } from "../types";
import { Empty, ErrorBox, Loading } from "../ui";
import { fmtDate } from "../utils";

export default function ReleasePage() {
  const rid = Number(useParams().rid);
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["release", rid], queryFn: () => api<ReleaseDetail>(`/releases/${rid}`), enabled: isValidId(rid) });
  const [from, setFrom] = useState<number | "">("");
  const [to, setTo] = useState<number | "">("");

  if (!isValidId(rid))
    return (
      <Empty title="That release does not exist">
        <Link to="/">Go to your releases</Link>
      </Empty>
    );
  if (q.isLoading) return <Loading label="Loading release…" />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const release = q.data!;
  const canCompare = release.versions.length >= 2;
  const invalidPair = from === "" || to === "" || from === to;
  const options = release.versions.map((v) => (
    <option key={v.id} value={v.version_no}>
      Version {v.version_no}
    </option>
  ));

  return (
    <>
      <Link to="/" className="back">
        ← All releases
      </Link>
      <div className="page-head">
        <div>
          <h1>{release.name}</h1>
          <div className="sub">Created {fmtDate(release.created_at)}</div>
        </div>
        <Link className="btn btn-primary" to={`/releases/${rid}/versions/new`}>
          {release.versions.length ? "Save a new version" : "Add the release package"}
        </Link>
      </div>

      {release.versions.length === 0 ? (
        <p className="muted">This release has no package yet. Add one to start.</p>
      ) : (
        <ul className="release-list">
          {[...release.versions].reverse().map((v) => (
            <li key={v.id} className="release-row">
              <div>
                <Link to={`/versions/${v.id}`} className="title">
                  Version {v.version_no}
                </Link>
                <div className="muted small">
                  {fmtDate(v.created_at)}, {v.has_analysis ? "analysed" : Object.keys(v.statement_counts).length > 0 ? "statements carried over" : "not analysed yet"}
                  {Object.entries(v.statement_counts).map(([k, n]) => `, ${n} ${k}`)}
                </div>
              </div>
              <span className="badge badge-plain">{v.review_state.replace("_", " ")}</span>
            </li>
          ))}
        </ul>
      )}

      {canCompare && (
        <section className="section">
          <h2>Compare two versions</h2>
          <p className="muted">See which items were added, removed or changed, and which statements went stale as a result.</p>
          <div className="row">
            <div>
              <label htmlFor="cmp-from">From</label>
              <select id="cmp-from" value={from} onChange={(e) => setFrom(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Choose a version</option>
                {options}
              </select>
            </div>
            <div>
              <label htmlFor="cmp-to">To</label>
              <select id="cmp-to" value={to} onChange={(e) => setTo(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Choose a version</option>
                {options}
              </select>
            </div>
            <button className="btn btn-primary" disabled={invalidPair} onClick={() => nav(`/releases/${rid}/compare?from=${from}&to=${to}`)}>
              Compare versions
            </button>
          </div>
          {from !== "" && from === to && <div className="field-error">Choose two different versions.</div>}
        </section>
      )}
    </>
  );
}
