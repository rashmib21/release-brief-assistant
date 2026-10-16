import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, post } from "../api";
import type { ReleaseRow } from "../types";
import { ErrorBox, Loading, useToast } from "../ui";
import { fmtDate } from "../utils";

const FLOW = [
  ["Enter the release package", "Features, fixes, behaviour changes, QA, limits, migration notes, affected users."],
  ["Run the section check", "Plain code confirms every section is filled in. No AI involved."],
  ["Let the AI draft", "It rates impact, finds gaps, flags claims QA does not back, and writes two summaries."],
  ["Review every statement", "Edit, approve or reject. Each one links to the evidence it rests on."],
  ["Generate the final brief", "Only statements you approved make it in."],
];

export default function ReleasesPage() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [search, setSearch] = useState("");

  const releases = useQuery({ queryKey: ["releases"], queryFn: () => api<ReleaseRow[]>("/releases") });

  const create = useMutation({
    mutationFn: () => post<{ id: number }>("/releases", { name: name.trim() }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["releases"] });
      nav(`/releases/${r.id}/versions/new`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const sample = useMutation({
    mutationFn: () => post<{ id: number; version_id: number }>("/releases/sample"),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["releases"] });
      toast("Sample release loaded. Run the AI analysis to try the workflow.");
      nav(`/versions/${r.version_id}`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const nameError = touched && !name.trim() ? "Enter a release name, for example “Mobile app 2.3”." : null;
  const hasReleases = !!releases.data && releases.data.length > 0;
  const allReleases = releases.data ?? [];
  const filteredReleases = allReleases.filter((r) => r.name.toLowerCase().includes(search.toLowerCase()));
  const inReview = allReleases.filter((r) => r.latest_version?.review_state === "in_review").length;
  const drafts = allReleases.filter((r) => !r.latest_version || r.latest_version.review_state === "draft").length;

  return (
    <>
      <section className="dashboard-welcome">
        <div className="welcome-copy">
          <div className="eyebrow"><span className="eyebrow-dot" /> RELEASE WORKSPACE</div>
          <h1>Your releases,<br /><span>clearly communicated.</span></h1>
          <p>Turn release details into evidence-backed updates for engineers, stakeholders, and clients. You stay in control of every statement.</p>
          <div className="welcome-actions">
            <a className="btn btn-primary" href="#create-release">＋ Create new release</a>
            <button className="btn btn-soft" onClick={() => sample.mutate()} disabled={sample.isPending}>
              {sample.isPending ? "Loading sample…" : "Explore sample release ↗"}
            </button>
          </div>
          <div className="trust-note"><span className="trust-check">✓</span> AI drafts only · Human review required · No deployment actions</div>
        </div>
        <div className="welcome-visual" aria-hidden="true">
          <div className="visual-orbit orbit-one" /><div className="visual-orbit orbit-two" />
          <div className="visual-document"><div className="doc-top"><span /><span /><span /></div><div className="doc-label">RELEASE BRIEF <b>v2.3</b></div><div className="doc-line wide" /><div className="doc-line" /><div className="doc-highlight" /><div className="doc-line wide" /><div className="doc-line short" /><div className="doc-approved"><span>✓</span><div><b>Evidence checked</b><small>Ready for your review</small></div></div></div>
          <div className="floating-chip chip-top"><span>✦</span> AI-assisted drafts</div><div className="floating-chip chip-bottom"><span>✓</span> You approve every claim</div>
        </div>
      </section>

      <section className="stat-grid" aria-label="Release overview">
        <article className="stat-card"><div className="stat-icon stat-purple">▤</div><div><span>Total releases</span><strong>{releases.isLoading ? "—" : allReleases.length}</strong><small>Across your workspace</small></div><span className="stat-mark">↗</span></article>
        <article className="stat-card"><div className="stat-icon stat-amber">◷</div><div><span>Drafts</span><strong>{releases.isLoading ? "—" : drafts}</strong><small>Waiting for review</small></div><span className="stat-mark">↗</span></article>
        <article className="stat-card"><div className="stat-icon stat-green">✓</div><div><span>In review</span><strong>{releases.isLoading ? "—" : inReview}</strong><small>Review in progress</small></div><span className="stat-mark">↗</span></article>
      </section>

      <section className="new-release dashboard-create" id="create-release">
        <div className="create-heading"><div><span className="section-kicker">GET STARTED</span><h2>Create a release</h2><p>Start with a name. You’ll add features, fixes, QA, and other release details next.</p></div><div className="create-symbol">＋</div></div>
        <form className="create-form" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (name.trim()) create.mutate(); }}>
          <div className="grow"><label htmlFor="rel-name">Release name</label><input id="rel-name" placeholder="e.g. Mobile app 2.4" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} onBlur={() => setTouched(true)} aria-invalid={!!nameError} aria-describedby={nameError ? "rel-name-err" : undefined} />{nameError && <div id="rel-name-err" className="field-error">{nameError}</div>}</div>
          <button className="btn btn-primary" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create release →"}</button>
        </form>
      </section>

      <section className="releases-section">
        <div className="releases-heading"><div><span className="section-kicker">YOUR WORKSPACE</span><h2>Recent releases <span className="count-pill">{allReleases.length}</span></h2><p>Track versions and continue where you left off.</p></div><div className="release-search"><span>⌕</span><input aria-label="Search releases" placeholder="Search releases…" value={search} onChange={(e) => setSearch(e.target.value)} /></div></div>
        {releases.isLoading && <Loading label="Loading releases…" />}
        {releases.isError && <ErrorBox error={releases.error} onRetry={() => releases.refetch()} />}
        {releases.data && !hasReleases && <div className="dashboard-empty"><div className="empty-illustration">▤</div><h3>Your workspace is ready</h3><p>Create your first release or load the sample to explore the review workflow.</p><button className="btn btn-primary" onClick={() => sample.mutate()} disabled={sample.isPending}>{sample.isPending ? "Loading sample…" : "Load sample release"}</button></div>}
        {hasReleases && filteredReleases.length === 0 && <div className="dashboard-empty compact-empty"><h3>No matching releases</h3><p>Try another search term.</p></div>}
        {filteredReleases.length > 0 && <ul className="release-list dashboard-release-list">{filteredReleases.map((r) => {
          const state = r.latest_version?.review_state ?? "draft";
          return <li key={r.id} className="release-row dashboard-release-row"><div className="release-avatar">{r.name.trim().charAt(0).toUpperCase()}</div><div className="release-info"><Link to={r.latest_version ? `/versions/${r.latest_version.id}` : `/releases/${r.id}`} className="title">{r.name}</Link><div className="release-meta"><span>{r.version_count} version{r.version_count === 1 ? "" : "s"}</span><span className="meta-dot">·</span><span>Created {fmtDate(r.created_at)}</span></div></div><div className="release-row-actions"><span className={`status-pill status-${state.replace("_", "-")}`}><i />{state.replace("_", " ")}</span><Link className="btn btn-small btn-open" to={`/releases/${r.id}`}>View versions <span>→</span></Link></div></li>;
        })}</ul>}
      </section>
    </>
  );
}
