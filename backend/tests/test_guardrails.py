import pytest

from app.schemas import StatementOut, StatementsOutput
from app.services.guardrails import GuardrailError, check_statements, deterministic_flags
from app.services.package import normalize_package

PKG = normalize_package(
    {
        "features": [{"text": "F"}],
        "bug_fixes": [{"text": "None"}],
        "changed_behaviour": [{"text": "None"}],
        "qa_summary": [{"text": "Q", "covers": ["F1"]}],
        "known_limitations": [{"text": "L"}],
        "migration_notes": [{"text": "None"}],
        "affected_user_groups": [{"text": "U"}],
    }
)


def stmt(audience, section, cites):
    return StatementOut(audience=audience, section=section, text="x", citations=cites)


def full(extra=None):
    base = [stmt(a, s, ["F1", "Q1"] if s == "summary" else ["L1"]) for a in ("technical", "client") for s in ("summary", "risks")]
    return StatementsOutput(statements=base + (extra or []))


def test_valid_output_passes():
    check_statements(full(), PKG)


def test_fake_citation_rejected():
    with pytest.raises(GuardrailError) as e:
        check_statements(full([stmt("technical", "summary", ["F99"])]), PKG)
    assert "unknown item F99" in str(e.value)


def test_statement_without_citation_rejected():
    with pytest.raises(GuardrailError) as e:
        check_statements(full([stmt("client", "summary", [])]), PKG)
    assert "no citation" in str(e.value)


def test_each_audience_needs_a_risks_statement():
    out = StatementsOutput(statements=[s for s in full().statements if not (s.audience == "client" and s.section == "risks")])
    with pytest.raises(GuardrailError) as e:
        check_statements(out, PKG)
    assert "missing risks statement for client" in str(e.value)


def test_claim_without_qa_citation_is_flagged():
    assert deterministic_flags(["F1"])[0]["code"] == "no_qa_citation"
    assert deterministic_flags(["F1", "Q1"]) == []
    assert deterministic_flags(["L1"]) == []
