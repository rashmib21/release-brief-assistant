"""Helpers for the release package: normalising, ID assignment and hashing.

A release package is a dict of 7 sections. Every item has a stable ID such as F1 or Q2,
so AI statements can cite items and we can later tell which cited items changed.
"""
import hashlib
import json
import re

# section key -> (ID prefix, label)
SECTIONS: dict[str, tuple[str, str]] = {
    "features": ("F", "Completed features"),
    "bug_fixes": ("B", "Bug fixes"),
    "changed_behaviour": ("C", "Changed behaviour"),
    "qa_summary": ("Q", "QA summary"),
    "known_limitations": ("L", "Known limitations"),
    "migration_notes": ("M", "Migration or configuration notes"),
    "affected_user_groups": ("U", "Affected user groups"),
}
CLAIM_SECTIONS = ("features", "bug_fixes", "changed_behaviour")  # things QA should back up
CLAIM_PREFIXES = tuple(SECTIONS[s][0] for s in CLAIM_SECTIONS)

NONE_WORDS = {"none", "n/a", "na", "nil", "not applicable", "no limitations", "no changes"}


def is_none_text(text: str) -> bool:
    return text.strip().strip(".").lower() in NONE_WORDS


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control(text: str) -> str:
    """Remove NUL and other control characters. Postgres refuses NUL bytes, which would be a 500."""
    return _CONTROL_CHARS.sub("", text)


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", strip_control(str(text or ""))).strip()


def normalize_package(raw: dict) -> dict:
    """Trim text, drop non-dict items, assign missing/duplicate-free IDs by section prefix."""
    out: dict[str, list[dict]] = {}
    for key, (prefix, _label) in SECTIONS.items():
        items_in = raw.get(key) or []
        used = {strip_control(str(i.get("id"))).strip().upper() for i in items_in if isinstance(i, dict) and i.get("id")}
        counter = 1
        items_out = []
        for item in items_in:
            if not isinstance(item, dict):
                continue
            item_id = strip_control(str(item.get("id") or "")).strip().upper()
            if not item_id:
                while f"{prefix}{counter}" in used:
                    counter += 1
                item_id = f"{prefix}{counter}"
                used.add(item_id)
            entry = {"id": item_id, "text": _clean(item.get("text"))}
            if key == "qa_summary":
                covers = item.get("covers") or []
                entry["covers"] = sorted({strip_control(str(c)).strip().upper() for c in covers if strip_control(str(c)).strip()})
            items_out.append(entry)
        out[key] = items_out
    return out


def item_index(package: dict) -> dict[str, dict]:
    """id -> {"section": key, "item": {...}}"""
    index: dict[str, dict] = {}
    for key in SECTIONS:
        for item in package.get(key, []):
            index[item["id"]] = {"section": key, "item": item}
    return index


def item_hash(item: dict) -> str:
    payload = {"text": _clean(item.get("text")).lower(), "covers": sorted(item.get("covers", []))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def compute_hashes(package: dict) -> dict[str, str]:
    return {item_id: item_hash(entry["item"]) for item_id, entry in item_index(package).items()}


def qa_coverage(package: dict) -> dict[str, list[str]]:
    """For each feature/bug fix/behaviour change, the QA items that declare they cover it."""
    coverage: dict[str, list[str]] = {}
    for key in CLAIM_SECTIONS:
        for item in package.get(key, []):
            coverage[item["id"]] = []
    for qa in package.get("qa_summary", []):
        for target in qa.get("covers", []):
            if target in coverage:
                coverage[target].append(qa["id"])
    return coverage
