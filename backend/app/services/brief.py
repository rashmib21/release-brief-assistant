"""Final reviewed brief: built only from statements a human approved."""
from datetime import datetime, timezone

from ..models import Analysis, ReleaseVersion, Statement

DISCLAIMER = (
    "> This brief is NOT a release approval and does not deploy anything. "
    "It contains only statements a person reviewed and approved. "
    "Release approval is a separate human decision."
)


def effective_text(s: Statement) -> str:
    return (s.edited_text or s.text).strip()


def blocking_statements(statements: list[Statement]) -> list[Statement]:
    return [s for s in statements if s.status in ("draft", "stale")]


def _line(s: Statement) -> str:
    cites = ", ".join(c["id"] for c in s.citations_json)
    note = " (no QA evidence cited)" if any(f["code"] == "no_qa_citation" for f in (s.flags_json or [])) else ""
    return f"- {effective_text(s)} [{cites}]{note}"


def build_brief(version: ReleaseVersion, statements: list[Statement], analysis: Analysis | None, release_name: str) -> str:
    approved = [s for s in statements if s.status == "approved"]
    lines = [
        f"# Release brief: {release_name}, version {version.version_no}",
        "",
        DISCLAIMER,
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    for audience, title in (("technical", "Technical summary"), ("client", "Summary for stakeholders and clients")):
        lines += [f"## {title}", ""]
        summary = [s for s in approved if s.audience == audience and s.section == "summary"]
        risks = [s for s in approved if s.audience == audience and s.section == "risks"]
        lines += [_line(s) for s in summary] or ["- No approved summary statements."]
        lines += ["", "### Known risks and limitations", ""]
        lines += [_line(s) for s in risks] or ["- No approved risk statements."]
        lines.append("")
    if analysis:
        lines += ["## Open flags from analysis", "", "### Missing information", ""]
        lines += [f"- {m['topic']}: {m['why_it_matters']}" for m in analysis.missing_info_json] or ["- None identified."]
        lines += ["", "### Claims not supported by QA evidence", ""]
        lines += [f"- {u['claim_item_id']}: {u['claim']} ({u['reason']})" for u in analysis.unsupported_claims_json] or ["- None identified."]
        lines.append("")
    return "\n".join(lines)
