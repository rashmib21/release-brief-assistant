"""Version comparison and stale-statement detection (deterministic)."""
from ..models import Statement
from .package import SECTIONS, compute_hashes


def stale_reason(citations: list[dict], current_hashes: dict[str, str]) -> str | None:
    """Return why a statement is stale, or None if every cited item is unchanged."""
    reasons = []
    for cite in citations:
        cid = cite["id"]
        if cid not in current_hashes:
            reasons.append(f"{cid} was removed")
        elif current_hashes[cid] != cite["hash"]:
            reasons.append(f"{cid} changed")
    return "; ".join(reasons) if reasons else None


def carry_statements(previous: list[Statement], new_hashes: dict[str, str]) -> list[Statement]:
    """Copy statements from the previous version into a new one and mark stale ones."""
    carried = []
    for old in previous:
        reason = stale_reason(old.citations_json, new_hashes)
        if reason:
            status = "stale" if old.status != "rejected" else "rejected"
        elif old.status == "stale":
            status = "draft"  # cited items match again (change was reverted); needs a fresh look
        else:
            status = old.status
        carried.append(
            Statement(
                audience=old.audience,
                section=old.section,
                text=old.text,
                edited_text=old.edited_text,
                citations_json=list(old.citations_json),
                flags_json=list(old.flags_json or []),
                status=status,
                stale_reason=reason if status == "stale" else None,
                carried_from_id=old.id,
            )
        )
    return carried


def compare_packages(a: dict, b: dict) -> dict:
    """Field-level diff between two packages: added, removed, changed items per section."""
    sections = {}
    totals = {"added": 0, "removed": 0, "changed": 0}
    for key, (_prefix, label) in SECTIONS.items():
        a_items = {i["id"]: i for i in a.get(key, [])}
        b_items = {i["id"]: i for i in b.get(key, [])}
        added = [b_items[i] for i in b_items if i not in a_items]
        removed = [a_items[i] for i in a_items if i not in b_items]
        changed = []
        for i in a_items:
            if i in b_items and compute_hashes({key: [a_items[i]]}) != compute_hashes({key: [b_items[i]]}):
                changed.append({"id": i, "before": a_items[i], "after": b_items[i]})
        sections[key] = {"label": label, "added": added, "removed": removed, "changed": changed}
        totals["added"] += len(added)
        totals["removed"] += len(removed)
        totals["changed"] += len(changed)
    return {"sections": sections, "totals": totals}
