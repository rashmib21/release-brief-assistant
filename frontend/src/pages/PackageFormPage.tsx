import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, isValidId, post } from "../api";
import type { Package, ReleaseDetail, VersionDetail, VersionSummary } from "../types";
import { Empty, ErrorBox, Loading, useToast } from "../ui";
import { SECTIONS, allIds, blankSections, claimItems, emptyPackage, isNoneText, nextId } from "../utils";

/** mode "new": save as a new version of a release (prefilled from the latest version).
 *  mode "edit": fix typos in a version that has not been analysed yet. */
export default function PackageFormPage({ mode }: { mode: "new" | "edit" }) {
  const params = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const rid = Number(params.rid);
  const vid = Number(params.vid);

  const release = useQuery({ queryKey: ["release", rid], queryFn: () => api<ReleaseDetail>(`/releases/${rid}`), enabled: mode === "new" && isValidId(rid) });
  const latestId = mode === "new" ? release.data?.versions.at(-1)?.id : vid;
  const source = useQuery({ queryKey: ["version", latestId], queryFn: () => api<VersionDetail>(`/versions/${latestId}`), enabled: !!latestId && isValidId(latestId) });

  const [pkg, setPkg] = useState<Package | null>(null);
  const [dirty, setDirty] = useState(false);
  // Ask before the tab closes with unsaved typing.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (pkg) return;
    if (mode === "new" && release.data && release.data.versions.length === 0) setPkg(emptyPackage());
    if (source.data) {
      const copy: Package = JSON.parse(JSON.stringify(source.data.package));
      for (const s of SECTIONS) if (!copy[s.key]?.length) copy[s.key] = [{ id: `${s.prefix}1`, text: "" }];
      setPkg(copy);
    }
  }, [mode, release.data, source.data, pkg]);

  const save = useMutation({
    mutationFn: (p: Package) => {
      const cleaned: Package = {};
      for (const s of SECTIONS) cleaned[s.key] = (p[s.key] ?? []).filter((i) => i.text.trim());
      return mode === "new" ? post<VersionSummary>(`/releases/${rid}/versions`, { package: cleaned }) : api<VersionDetail>(`/versions/${vid}/package`, { method: "PUT", body: JSON.stringify(cleaned) });
    },
    onSuccess: (res) => {
      setDirty(false);
      qc.invalidateQueries();
      toast(mode === "new" ? "Version saved." : "Package saved.");
      nav(`/versions/${res.id}`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const backTo = mode === "new" ? `/releases/${rid}` : `/versions/${vid}`;
  const back = (
    <Link to={backTo} className="back">
      ← Back
    </Link>
  );

  if (!isValidId(mode === "new" ? rid : vid))
    return (
      <Empty title="That page does not exist">
        <Link to="/">Go to your releases</Link>
      </Empty>
    );
  if (mode === "new" && release.isLoading) return <Loading label="Loading the release…" />;
  if (release.isError) return <ErrorBox error={release.error} onRetry={() => release.refetch()} />;
  if (source.isError) return <ErrorBox error={source.error} onRetry={() => source.refetch()} />;
  if (!pkg) return <Loading label="Preparing the form…" />;

  const update = (key: string, items: Package[string]) => {
    setDirty(true);
    setPkg({ ...pkg, [key]: items });
  };
  const ids = allIds(pkg);
  const blanks = blankSections(pkg);
  const claims = claimItems(pkg);
  const prev = release.data?.versions.at(-1);

  return (
    <>
      {back}
      <div className="page-head">
        <div>
          <h1>{mode === "new" ? (prev ? "Save a new version" : "Release package") : "Edit the package"}</h1>
          <div className="sub">Each item has an ID (F1, B1, and so on). The AI cites these IDs, so keep them the same between versions. If a section has nothing to report, write “None” rather than leaving it blank.</div>
        </div>
      </div>
      {mode === "new" && prev && (
        <div className="alert alert-info">This form starts from version {prev.version_no}. Any statement that cites an item you change will be marked out of date.</div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(pkg);
        }}
      >
        {SECTIONS.map((s) => {
          const items = pkg[s.key] ?? [];
          const empty = !items.some((i) => i.text.trim());
          const blankItem = { id: nextId(s.prefix, ids), text: "", ...(s.key === "qa_summary" ? { covers: [] as string[] } : {}) };
          return (
            <section key={s.key} className="form-section" aria-labelledby={`h-${s.key}`}>
              <div>
                <h2 id={`h-${s.key}`}>{s.label}</h2>
                <p className="hint">{s.hint}</p>
                <button
                  type="button"
                  className="btn btn-small"
                  style={{ marginTop: "0.5rem" }}
                  onClick={() => {
                    if (items.some((i) => i.text.trim() && !isNoneText(i.text)) && !confirm(`Replace the items in “${s.label}” with None?`)) return;
                    update(s.key, [{ id: items[0]?.id ?? `${s.prefix}1`, text: "None", ...(s.key === "qa_summary" ? { covers: [] } : {}) }]);
                  }}
                >
                  Nothing to report
                </button>
              </div>
              <div>
                {items.map((item, idx) => (
                  <div key={item.id} className="item-row">
                    <span className="chip chip-id">{item.id}</span>
                    <div className="grow">
                      <label className="sr-only" htmlFor={`t-${item.id}`}>{`${s.label}, item ${item.id}`}</label>
                      <textarea id={`t-${item.id}`} rows={2} maxLength={1000} value={item.text} onChange={(e) => update(s.key, items.map((x, i) => (i === idx ? { ...x, text: e.target.value } : x)))} />
                      {item.text.length >= 850 && <div className="small muted">{item.text.length} / 1000 characters</div>}
                      {s.key === "qa_summary" && claims.length > 0 && (
                        <fieldset className="covers">
                          <legend>This test covers</legend>
                          {claims.map((c) => (
                            <label key={c.id} className="check">
                              <input
                                type="checkbox"
                                checked={(item.covers ?? []).includes(c.id)}
                                onChange={(e) => {
                                  const set = new Set(item.covers ?? []);
                                  e.target.checked ? set.add(c.id) : set.delete(c.id);
                                  update(s.key, items.map((x, i) => (i === idx ? { ...x, covers: [...set] } : x)));
                                }}
                              />
                              {c.id}
                            </label>
                          ))}
                        </fieldset>
                      )}
                    </div>
                    <button type="button" className="btn btn-small" aria-label={`Remove ${item.id}`} onClick={() => update(s.key, items.length > 1 ? items.filter((_, i) => i !== idx) : [{ ...item, text: "", covers: item.covers ? [] : undefined }])}>
                      Remove
                    </button>
                  </div>
                ))}
                <button type="button" className="btn btn-small" onClick={() => update(s.key, [...items, blankItem])}>
                  Add an item
                </button>
                {empty && <div className="field-error">This section is empty. Add an item, or choose “Nothing to report”, before you run the AI analysis.</div>}
              </div>
            </section>
          );
        })}

        <div className="save-bar">
          <button className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : mode === "new" ? "Save version" : "Save changes"}
          </button>
          {blanks.length > 0 ? <span className="muted small">You can save now. The AI analysis stays off until these have content: {blanks.join(", ")}.</span> : <span className="muted small">All sections have content.</span>}
        </div>
        {save.isError && <ErrorBox error={save.error} />}
      </form>
    </>
  );
}
