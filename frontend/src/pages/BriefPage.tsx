import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError, api, isValidId } from "../api";
import { Empty, ErrorBox, Loading, useToast } from "../ui";
import { mdToBlocks } from "../utils";

export default function BriefPage() {
  const vid = Number(useParams().vid);
  const toast = useToast();
  const q = useQuery({ queryKey: ["brief", vid], queryFn: () => api<{ content_md: string; created_at: string }>(`/versions/${vid}/final-brief`), enabled: isValidId(vid) });

  const back = (
    <Link to={`/versions/${vid}`} className="back">
      ← Back to the review
    </Link>
  );

  if (q.isLoading) return <Loading label="Loading the brief…" />;
  if (!isValidId(vid) || (q.error instanceof ApiError && q.error.status === 404))
    return (
      <>
        {back}
        <Empty title="There is no final brief yet">
          <p>Approve or reject every statement, then generate the brief from the review page.</p>
        </Empty>
      </>
    );
  if (q.isError)
    return (
      <>
        {back}
        <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      </>
    );
  const md = q.data!.content_md;

  async function copy() {
    try {
      await navigator.clipboard.writeText(md);
      toast("Brief copied as Markdown.");
    } catch {
      toast("Copying was blocked by the browser. Download the file instead.", "error");
    }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `release-brief-v${vid}.md`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Brief downloaded.");
  }

  return (
    <>
      {back}
      <div className="toolbar row between">
        <span className="muted small">Only statements you approved are included.</span>
        <div className="row">
          <button className="btn" onClick={copy}>
            Copy Markdown
          </button>
          <button className="btn btn-primary" onClick={download}>
            Download Markdown
          </button>
        </div>
      </div>
      <article className="brief">
        {mdToBlocks(md).map((b, i) => {
          if (b.type === "h1") return <h1 key={i}>{b.text}</h1>;
          if (b.type === "h2") return <h2 key={i}>{b.text}</h2>;
          if (b.type === "h3") return <h3 key={i}>{b.text}</h3>;
          if (b.type === "quote") return <blockquote key={i} className="disclaimer">{b.text}</blockquote>;
          if (b.type === "li") return <p key={i} className="brief-li">{b.text}</p>;
          return <p key={i}>{b.text}</p>;
        })}
      </article>
    </>
  );
}
