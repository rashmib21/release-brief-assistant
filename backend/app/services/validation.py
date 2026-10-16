"""Deterministic checks on the release package. No AI involved.

Blank section = error. An explicit "None" / "N/A" item = pass.
"""
from .package import CLAIM_SECTIONS, SECTIONS, is_none_text, item_index, qa_coverage


def _real_items(items: list[dict]) -> list[dict]:
    return [i for i in items if i["text"] and not is_none_text(i["text"])]


def validate_package(package: dict) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    seen: dict[str, str] = {}
    for key, (_prefix, label) in SECTIONS.items():
        items = package.get(key, [])
        filled = [i for i in items if i["text"]]
        if not filled:
            errors.append(
                {
                    "code": "missing_section",
                    "section": key,
                    "message": f'"{label}" is empty. Add an item, or write "None" if there is nothing to report.',
                }
            )
        elif len(filled) > 1 and any(is_none_text(i["text"]) for i in filled):
            warnings.append(
                {
                    "code": "none_mixed",
                    "section": key,
                    "message": f'"{label}" has both "None" and real items. Remove the "None" entry.',
                }
            )
        for item in items:
            if not item["text"]:
                errors.append(
                    {
                        "code": "blank_item",
                        "section": key,
                        "item_id": item["id"],
                        "message": f"{item['id']} has no text. Fill it or remove it.",
                    }
                )
            if item["id"] in seen:
                errors.append(
                    {
                        "code": "duplicate_id",
                        "section": key,
                        "item_id": item["id"],
                        "message": f"ID {item['id']} is used more than once.",
                    }
                )
            seen[item["id"]] = key

    index = item_index(package)
    for qa in package.get("qa_summary", []):
        for target in qa.get("covers", []):
            if target not in index or index[target]["section"] not in CLAIM_SECTIONS:
                errors.append(
                    {
                        "code": "bad_qa_link",
                        "section": "qa_summary",
                        "item_id": qa["id"],
                        "message": f"{qa['id']} says it covers {target}, which is not a feature, bug fix or behaviour change.",
                    }
                )

    for item_id, qa_ids in qa_coverage(package).items():
        text = index[item_id]["item"]["text"]
        if text and not is_none_text(text) and not qa_ids:
            warnings.append(
                {
                    "code": "no_qa_coverage",
                    "section": index[item_id]["section"],
                    "item_id": item_id,
                    "message": f"No QA item is linked to {item_id}. Any claim about it will be flagged as unsupported.",
                }
            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}
