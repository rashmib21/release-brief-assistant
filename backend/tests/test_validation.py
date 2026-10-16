from app.services.package import normalize_package
from app.services.validation import validate_package


def pkg(**over):
    base = {
        "features": [{"text": "A feature"}],
        "bug_fixes": [{"text": "None"}],
        "changed_behaviour": [{"text": "N/A"}],
        "qa_summary": [{"text": "Tested", "covers": ["F1"]}],
        "known_limitations": [{"text": "None"}],
        "migration_notes": [{"text": "None"}],
        "affected_user_groups": [{"text": "Customers"}],
    }
    base.update(over)
    return normalize_package(base)


def codes(result):
    return {e["code"] for e in result["errors"]}


def test_complete_package_with_explicit_none_passes():
    assert validate_package(pkg())["valid"] is True


def test_blank_section_is_an_error():
    result = validate_package(pkg(known_limitations=[]))
    assert not result["valid"]
    assert "missing_section" in codes(result)


def test_whitespace_only_item_counts_as_blank():
    result = validate_package(pkg(migration_notes=[{"text": "   "}]))
    assert "missing_section" in codes(result)


def test_duplicate_ids_rejected():
    result = validate_package(pkg(features=[{"id": "F1", "text": "a"}, {"id": "F1", "text": "b"}]))
    assert "duplicate_id" in codes(result)


def test_qa_link_to_unknown_item_rejected():
    result = validate_package(pkg(qa_summary=[{"text": "Tested", "covers": ["F9"]}]))
    assert "bad_qa_link" in codes(result)


def test_feature_without_qa_gets_warning_not_error():
    result = validate_package(pkg(qa_summary=[{"text": "Tested something else"}]))
    assert result["valid"]
    assert any(w["code"] == "no_qa_coverage" and w["item_id"] == "F1" for w in result["warnings"])
