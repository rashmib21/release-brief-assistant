import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, api, isValidId, post } from "../api";
import Stepper from "../Stepper";
import type { Package, Validation, VersionDetail } from "../types";
import { AnalysisProgress, Empty, ErrorBox, ImpactBadge, Loading, useToast } from "../ui";
import { SECTIONS, fmtDate } from "../utils";
import StatementCard from "./StatementCard";

const CLAIM_KEYS = ["features", "bug_fixes", "changed_behaviour"];

function Manifest({ pkg }: { pkg: Package }) {
  return (
    <dl className="manifest">
      {SECTIONS.map((s) => (
        <div key={s.key} style={{ display: "contents" }}>
          <dt>{s.label}</dt>
          <dd>
            <ul>
              {(pkg[s.key] ?? []).map((i) => (
                <li key={i.id}>
                  <span className="chip chip-id">{i.id}</span> {i.text}
                  {i.covers && i.covers.length > 0 && <span className="muted small"> (tests {i.covers.join(", ")})</span>}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Right-hand rail: shows the exact item a statement rests on, with the QA that backs it. */
function Evidence({ pkg, cid }: { pkg: Package; cid: string | null }) {
  if (!cid) return <p className="rail-hint">Select an evidence chip, such as F1 or Q2, on any statement to see the exact item it rests on.</p>;
  const section = SECTIONS.find((s) => (pkg[s.key] ?? []).some((i) => i.id === cid));
  const item = section && pkg[section.key].find((i) => i.id === cid);
  if (!section || !item) return <p className="rail-hint">{cid} is no longer in this package, so nothing can back this statement. Edit its evidence or reject it.</p>;

  const testedBy = (pkg.qa_summary ?? []).filter((q) => q.covers?.includes(cid));
  const isClaim = CLAIM_KEYS.includes(section.key);
  return (
    <div>
      <div className="ev-kind">
        {section.label}, item {cid}
      </div>
      <p className="ev-text">
        <mark>{item.text}</mark>
      </p>
      {isClaim && (
        <>
          <h3>QA evidence for this item</h3>
          {testedBy.length === 0 ? (
            <p className="rail-hint">No QA item is linked to {cid}. Treat any claim about it as unverified.</p>
          ) : (
            <ul className="plain">
              {testedBy.map((q) => (
                <li key={q.id}>
                  <span className="chip chip-id">{q.id}</span> {q.text}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {section.key === "qa_summary" && (item.covers?.length ?? 0) > 0 && (
        <p className="rail-hint">This test covers {item.covers!.join(", ")}.</p>
      )}
    </div>
  );
}

export default function ReviewPage() {
  const vid = Number(useParams().vid);
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [audience, setAudience] = useState<"technical" | "client">("technical");
  const [selected, setSelected] = useState<{ sid: number; cid: string } | null>(null);
  const [justAnalysed, setJustAnalysed] = useState(false);

  const validId = isValidId(vid);
  const q = useQuery({ queryKey: ["version", vid], queryFn: () => api<VersionDetail>(`/versions/${vid}`), enabled: validId });
  const validation = useQuery({
    queryKey: ["validate", vid, q.data?.package],
    queryFn: () => post<Validation>(`/versions/${vid}/validate`),
    enabled: !!q.data,
  });

  const analyze = useMutation({
    mutationFn: (force: boolean) => post<VersionDetail>(`/versions/${vid}/analyze?force=${force}`),
    onSuccess: (d) => {
      qc.setQueryData(["version", vid], d);
      qc.invalidateQueries({ queryKey: ["releases"] });
      setSelected(null);
      setJustAnalysed(true);
      toast("Analysis finished. Review each statement before you generate the brief.");
    },
    onError: (e: Error) => {
      if (e instanceof ApiError && e.status === 409 && e.detail?.needs_force) {
        if (confirm("Running the analysis again replaces every statement, including the ones you approved. Continue?")) analyze.mutate(true);
        return;
      }
      toast(e.message, "error");
    },
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => api(`/statements/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["version", vid] }),
  });

  const brief = useMutation({
    mutationFn: () => post(`/versions/${vid}/final-brief`),
    onSuccess: () => {
      qc.invalidateQueries();
      toast("Final brief generated.");
      nav(`/versions/${vid}/brief`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const briefError = brief.isError ? brief.error : null;

  if (!validId)
    return (
      <Empty title="That version does not exist">
        <Link to="/">Go to your releases</Link>
      </Empty>
    );
  if (q.isLoading) return <Loading label="Loading version…" />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const v = q.data!;
  const counts = v.statements.reduce<Record<string, number>>((a, s) => ({ ...a, [s.status]: (a[s.status] ?? 0) + 1 }), {});
  const unresolved = (counts.draft ?? 0) + (counts.stale ?? 0);
  const approved = counts.approved ?? 0;
  // A new version carries its statements over from the previous one (marking stale ones) but has no analysis of its own.
  const hasStatements = v.statements.length > 0;
  const analysed = v.analysis !== null || hasStatements;
  const canBrief = analysed && unresolved === 0 && approved > 0 && !v.locked;
  const invalid = !!validation.data && !validation.data.valid;
  const analyzeError = analyze.isError && !(analyze.error instanceof ApiError && analyze.error.status === 409 && analyze.error.detail?.needs_force) ? analyze.error : null;
  const shown = v.statements.filter((s) => s.audience === audience);
  const staleCount = counts.stale ?? 0;

  const reviewed = analysed && unresolved === 0 && approved > 0;
  const done = { package: true, check: !!validation.data?.valid, analyze: analysed, review: reviewed, brief: !!v.final_brief };

  // One clear next step, always visible in the rail.
  let next: { title: string; text: string; action?: ReactNode };
  if (v.final_brief) {
    next = { title: "The brief is ready", text: "This version is locked. Save a new version if the package changes.", action: <Link className="btn btn-primary" to={`/versions/${vid}/brief`}>Open the final brief</Link> };
  } else if (invalid) {
    next = {
      title: "Fill in the missing sections",
      text: "The AI analysis stays off until every section has an item or an explicit “None”.",
      action: !analysed ? <Link className="btn btn-primary" to={`/versions/${vid}/edit`}>Edit the package</Link> : <Link className="btn btn-primary" to={`/releases/${v.release_id}/versions/new`}>Save a new version</Link>,
    };
  } else if (!analysed) {
    next = {
      title: "Run the AI analysis",
      text: "It rates impact, finds gaps, flags claims the QA evidence does not support and drafts two summaries. This takes up to a minute.",
      action: (
        <button className="btn btn-primary" disabled={analyze.isPending || validation.isLoading} onClick={() => analyze.mutate(false)}>
          {analyze.isPending ? "Analysing…" : "Run the AI analysis"}
        </button>
      ),
    };
  } else if (unresolved > 0) {
    next = {
      title: `Review ${unresolved} statement${unresolved === 1 ? "" : "s"}`,
      text: staleCount > 0 ? `${staleCount} went out of date because the package changed. Re-check those first.` : "Approve, edit or reject each one. Select its evidence chips to see the proof.",
    };
  } else if (canBrief) {
    next = {
      title: "Generate the final brief",
      text: `${approved} approved statement${approved === 1 ? "" : "s"} will go into it. This is a summary, not a release approval.`,
      action: (
        <button className="btn btn-primary" disabled={brief.isPending} onClick={() => brief.mutate()}>
          {brief.isPending ? "Generating…" : "Generate the final brief"}
        </button>
      ),
    };
  } else {
    next = { title: "Approve at least one statement", text: "Every statement is rejected, so the brief would be empty." };
  }

  return (
    <>
      <Link to={`/releases/${v.release_id}`} className="back">
        ← {v.release_name}
      </Link>
      <div className="page-head">
        <div>
          <h1>
            {v.release_name}, version {v.version_no}
          </h1>
          <div className="sub">Saved {fmtDate(v.created_at)}</div>
        </div>
        <span className="badge badge-plain">{v.review_state.replace("_", " ")}</span>
      </div>

      <Stepper done={done} blocked={invalid ? "check" : undefined} />

      {v.locked && (
        <div className="alert alert-info">
          The final brief was generated, so this version is locked. <Link to={`/versions/${vid}/brief`}>Open the brief</Link>, or save a new version to change anything.
        </div>
      )}

      <div className="split">
        <div>
          <section className="section">
            <div className="section-head">
              <h2>
                <span className="n">1</span> Release package
              </h2>
              <div className="row">
                {!analysed && (
                  <Link className="btn btn-small" to={`/versions/${vid}/edit`}>
                    Edit package
                  </Link>
                )}
                <Link className="btn btn-small" to={`/releases/${v.release_id}/versions/new`}>
                  Save changes as a new version
                </Link>
              </div>
            </div>
            {analysed ? (
              <details className="fold">
                <summary>Show the release package ({Object.values(v.package).reduce((n, items) => n + items.length, 0)} items)</summary>
                <Manifest pkg={v.package} />
              </details>
            ) : (
              <Manifest pkg={v.package} />
            )}
          </section>

          <section className="section">
            <div className="section-head">
              <h2>
                <span className="n">2</span> Section check
              </h2>
            </div>
            {validation.isLoading && <Loading label="Checking sections…" />}
            {validation.isError && <ErrorBox error={validation.error} onRetry={() => validation.refetch()} />}
            {validation.data?.valid && <div className="alert alert-success">Every required section has content.</div>}
            {validation.data?.errors.map((e, i) => (
              <div key={i} className="alert alert-error">
                {e.message}
              </div>
            ))}
            {validation.data?.warnings.map((w, i) => (
              <div key={i} className="alert alert-warn">
                {w.message}
              </div>
            ))}
          </section>

          <section className="section">
            <div className="section-head">
              <h2>
                <span className="n">3</span> AI analysis
              </h2>
              {analysed && !v.locked && (
                <button className="btn btn-small" disabled={analyze.isPending || invalid} onClick={() => analyze.mutate(false)}>
                  {analyze.isPending ? "Analysing…" : v.analysis ? "Run again" : "Run the analysis"}
                </button>
              )}
            </div>
            {analyze.isPending && <AnalysisProgress />}
            {analyzeError && <ErrorBox error={analyzeError} onRetry={() => analyze.mutate(analyze.variables ?? false)} />}
            {!analysed && !analyze.isPending && !analyzeError && <p className="muted">Nothing here yet. Run the analysis from the panel on the right.</p>}
            {!v.analysis && hasStatements && !analyze.isPending && (
              <div className="alert alert-info">
                This version has no analysis of its own. Its statements were carried over from the previous version, and any that cite an item you changed are marked out of date. Resolve those below, or run the analysis again to refresh the findings (this replaces every statement).
              </div>
            )}

            {v.analysis && (
              <>
                <h3>Impact on users</h3>
                <div className="impact-summary">
                  {(["high", "medium", "low"] as const).map((lvl) => (
                    <span key={lvl} className={`badge impact-${lvl}`}>
                      {v.analysis!.classifications.filter((c) => c.impact === lvl).length} {lvl}
                    </span>
                  ))}
                  <span className="muted small">
                    {v.analysis.missing_info.length} gaps · {v.analysis.unsupported_claims.length} unsupported claims
                  </span>
                </div>
                <div>
                  {v.analysis.classifications.map((c) => (
                    <div key={c.item_id} className="impact-row">
                      <span className="chip chip-id">{c.item_id}</span>
                      <ImpactBadge impact={c.impact} />
                      <div className="body">
                        <div className="why">{c.reason}</div>
                        <div className="groups">Affects {c.user_groups.join(", ")}</div>
                      </div>
                    </div>
                  ))}
                </div>

                <h3>Information that is missing</h3>
                {v.analysis.missing_info.length === 0 ? (
                  <p className="muted">Nothing missing was found.</p>
                ) : (
                  v.analysis.missing_info.map((m, i) => (
                    <div key={i} className="finding finding-warn">
                      <strong>{m.topic}</strong>
                      <em>{m.why_it_matters}</em>
                      <div>
                        {m.related_ids.map((id) => (
                          <span key={id} className="chip chip-id">
                            {id}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}

                <h3>Claims the QA evidence does not support</h3>
                {v.analysis.unsupported_claims.length === 0 ? (
                  <p className="muted">Every claim is backed by the QA evidence you supplied.</p>
                ) : (
                  v.analysis.unsupported_claims.map((u, i) => (
                    <div key={i} className="finding finding-bad">
                      <span className="chip chip-id">{u.claim_item_id}</span> <strong>{u.claim}</strong>
                      <em>
                        {u.reason}
                        {u.qa_ids.length > 0 && ` Compared with ${u.qa_ids.join(", ")}.`}
                      </em>
                    </div>
                  ))
                )}
              </>
            )}
          </section>

          {analysed && (
            <section className="section">
              <div className="section-head">
                <h2>
                  <span className="n">4</span> Review the statements
                </h2>
              </div>
              <p className="muted">The AI only drafts. Nothing counts until you approve it.</p>
              {staleCount > 0 && (
                <div className="alert alert-warn">
                  <span>
                    {staleCount} statement{staleCount === 1 ? " is" : "s are"} out of date because the package changed after {staleCount === 1 ? "it was" : "they were"} written.
                  </span>
                </div>
              )}
              <div className="tabs" role="tablist" aria-label="Audience">
                {(["technical", "client"] as const).map((a) => (
                  <button key={a} role="tab" aria-selected={audience === a} className={`tab ${audience === a ? "tab-active" : ""}`} onClick={() => setAudience(a)}>
                    {a === "technical" ? "For engineers" : "For stakeholders and clients"}
                    <span className="tab-count">{v.statements.filter((s) => s.audience === a && (s.status === "draft" || s.status === "stale")).length || "✓"}</span>
                  </button>
                ))}
              </div>
              {(["summary", "risks"] as const).map((kind) => (
                <div key={kind}>
                  <h3 className="group-title">{kind === "summary" ? "What changed" : "Known risks and limitations"}</h3>
                  {shown
                    .filter((s) => s.section === kind)
                    .map((s) => (
                      <StatementCard
                        key={`${s.id}-${s.status}-${s.effective_text}`}
                        s={s}
                        locked={v.locked}
                        entering={justAnalysed}
                        selectedCite={selected?.sid === s.id ? selected.cid : null}
                        onSelectCite={(cid) => setSelected(cid ? { sid: s.id, cid } : null)}
                        onPatch={(id, body) => patch.mutateAsync({ id, body })}
                      />
                    ))}
                </div>
              ))}
            </section>
          )}
        </div>

        <aside className="rail" aria-label="Next step and evidence">
          <div className="rail-panel rail-next">
            <h2>{next.title}</h2>
            <p className="rail-hint">{next.text}</p>
            {next.action}
            {briefError && <ErrorBox error={briefError} onRetry={() => brief.mutate()} />}
            {analysed && hasStatements && (
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={v.statements.length} aria-valuenow={v.statements.length - unresolved} aria-label="Statements reviewed">
                <div className="progress-bar" style={{ width: `${((v.statements.length - unresolved) / v.statements.length) * 100}%` }} />
                <span className="small muted">
                  {v.statements.length - unresolved} of {v.statements.length} reviewed
                </span>
              </div>
            )}
            {analysed && (
              <div className="rail-counts">
                {["draft", "stale", "approved", "rejected"].map((k) => (
                  <span key={k} className={`badge badge-${k}`}>
                    {counts[k] ?? 0} {k}
                  </span>
                ))}
              </div>
            )}
          </div>
          {analysed && (
            <div className="rail-panel rail-evidence">
              <h2>Evidence</h2>
              <Evidence pkg={v.package} cid={selected?.cid ?? null} />
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
