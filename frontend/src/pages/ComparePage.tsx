import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, isValidId } from "../api";
import type { Comparison, Item } from "../types";
import { Empty, ErrorBox, Loading } from "../ui";

const ItemLine = ({ item }: { item: Item }) => (
  <>
    <span className="chip chip-id">{item.id}</span> {item.text}
  </>
);

const covers = (i: Item) => (i.covers?.length ? ` (tests ${i.covers.join(", ")})` : "");

export default function ComparePage() {
  const rid = Number(useParams().rid);
  const [sp] = useSearchParams();
  const from = Number(sp.get("from"));
  const to = Number(sp.get("to"));
  const q = useQuery({
    queryKey: ["compare", rid, from, to],
    queryFn: () => api<Comparison>(`/releases/${rid}/compare?from=${from}&to=${to}`),
    enabled: isValidId(rid) && isValidId(from) && isValidId(to),
  });

  const back = (
    <Link to={`/releases/${rid}`} className="back">
      ← Back to the release
    </Link>
  );

  if (!isValidId(rid) || !isValidId(from) || !isValidId(to))
    return (
      <>
        {back}
        <Empty title="Choose two versions to compare">
          <p>Open the release and pick a “From” and a “To” version.</p>
        </Empty>
      </>
    );
  if (q.isLoading) return <Loading label="Comparing versions…" />;
  if (q.isError)
    return (
      <>
        {back}
        <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      </>
    );

  const { diff, stale_statements: stale } = q.data!;
  const sections = Object.entries(diff.sections).filter(([, s]) => s.added.length + s.removed.length + s.changed.length > 0);

  return (
    <>
      {back}
      <div className="page-head">
        <div>
          <h1>
            Version {from} to version {to}
          </h1>
          <div className="sub">What changed in the package, and which statements no longer match it.</div>
        </div>
        <div className="row">
          <span className="badge badge-approved">{diff.totals.added} added</span>
          <span className="badge badge-rejected">{diff.totals.removed} removed</span>
          <span className="badge badge-stale">{diff.totals.changed} changed</span>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Package changes</h2>
        </div>
        {sections.length === 0 ? (
          <p className="muted">The two packages are identical.</p>
        ) : (
          sections.map(([key, s]) => (
            <div key={key}>
              <h3>{s.label}</h3>
              <div className="diff-grid">
                {s.added.map((i) => (
                  <div key={i.id} className="diff diff-added">
                    <span className="kind">Added</span>
                    <div>
                      <ItemLine item={i} />
                      {covers(i)}
                    </div>
                  </div>
                ))}
                {s.removed.map((i) => (
                  <div key={i.id} className="diff diff-removed">
                    <span className="kind">Removed</span>
                    <div>
                      <ItemLine item={i} />
                      {covers(i)}
                    </div>
                  </div>
                ))}
                {s.changed.map((c) => (
                  <div key={c.id} className="diff diff-changed">
                    <span className="kind">Changed</span>
                    <div>
                      <span className="chip chip-id">{c.id}</span>
                      <div className="before">{c.before.text + covers(c.before)}</div>
                      <div className="after">{c.after.text + covers(c.after)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>
            Statements from version {from} that are out of date in version {to}
          </h2>
        </div>
        {stale.length === 0 ? (
          <p className="muted">None. Every item those statements cite is unchanged.</p>
        ) : (
          stale.map((s) => (
            <div key={s.statement_id} className="finding finding-warn">
              <strong>{s.text}</strong>
              <em>
                {s.reason}. Written for {s.audience === "client" ? "stakeholders and clients" : "engineers"}, was {s.status}.
              </em>
            </div>
          ))
        )}
      </section>
    </>
  );
}
