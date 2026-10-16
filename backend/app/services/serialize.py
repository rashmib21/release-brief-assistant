from ..models import Release, ReleaseVersion, Statement
from .brief import effective_text
from .diffing import stale_reason
from .package import item_index


def statement_to_dict(s: Statement, package: dict) -> dict:
    index = item_index(package)
    citations = []
    for c in s.citations_json:
        entry = index.get(c["id"])
        citations.append(
            {
                "id": c["id"],
                "section": entry["section"] if entry else None,
                "item_text": entry["item"]["text"] if entry else None,
                "exists": entry is not None,
            }
        )
    return {
        "id": s.id,
        "version_id": s.version_id,
        "audience": s.audience,
        "section": s.section,
        "text": s.text,
        "edited_text": s.edited_text,
        "effective_text": effective_text(s),
        "citations": citations,
        "flags": s.flags_json or [],
        "status": s.status,
        "stale_reason": s.stale_reason,
        "carried_from_id": s.carried_from_id,
    }


def version_summary(v: ReleaseVersion) -> dict:
    counts: dict[str, int] = {}
    for s in v.statements:
        counts[s.status] = counts.get(s.status, 0) + 1
    return {
        "id": v.id,
        "release_id": v.release_id,
        "version_no": v.version_no,
        "review_state": v.review_state,
        "created_at": v.created_at.isoformat(),
        "has_analysis": v.analysis is not None,
        "statement_counts": counts,
    }


def version_detail(v: ReleaseVersion, release: Release) -> dict:
    analysis = None
    if v.analysis:
        analysis = {
            "classifications": v.analysis.classifications_json,
            "missing_info": v.analysis.missing_info_json,
            "unsupported_claims": v.analysis.unsupported_claims_json,
            "created_at": v.analysis.created_at.isoformat(),
        }
    brief = None
    if v.final_brief:
        brief = {"content_md": v.final_brief.content_md, "created_at": v.final_brief.created_at.isoformat()}
    return {
        **version_summary(v),
        "release_name": release.name,
        "package": v.package_json,
        "locked": v.review_state == "brief_generated",
        "analysis": analysis,
        "statements": [statement_to_dict(s, v.package_json) for s in v.statements],
        "final_brief": brief,
    }


def live_stale(statements: list[Statement], hashes: dict[str, str]) -> list[dict]:
    out = []
    for s in statements:
        if s.status == "rejected":
            continue  # a rejected statement never reaches a brief, and new versions keep it rejected, not stale
        reason = stale_reason(s.citations_json, hashes)
        if reason:
            out.append({"statement_id": s.id, "audience": s.audience, "text": effective_text(s), "reason": reason, "status": s.status})
    return out
