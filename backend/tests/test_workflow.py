import pytest

from app.llm.client import LLMError
from app.llm.mock import MockLLM
from app.models import AiRun
from app.db import SessionLocal
from app.schemas import StatementOut, StatementsOutput


def patch_llm(monkeypatch, llm):
    monkeypatch.setattr("app.routers.versions.get_llm_client", lambda: llm)


def ai_runs():
    with SessionLocal() as db:
        return [(r.step, r.status) for r in db.query(AiRun).order_by(AiRun.id)]


def test_analysis_saves_everything_as_draft_never_approved(analyzed):
    _rid, _vid, data = analyzed
    assert data["review_state"] == "in_review"
    assert data["statements"], "expected statements"
    assert {s["status"] for s in data["statements"]} == {"draft"}
    assert {s["audience"] for s in data["statements"]} == {"technical", "client"}
    for audience in ("technical", "client"):
        assert any(s["audience"] == audience and s["section"] == "risks" for s in data["statements"])
    assert all(s["citations"] for s in data["statements"])


def test_unsupported_claims_found_by_ai_and_by_deterministic_flag(analyzed):
    _rid, _vid, data = analyzed
    claimed = {u["claim_item_id"] for u in data["analysis"]["unsupported_claims"]}
    assert "F2" in claimed  # "all devices" vs QA "Android only"
    assert "C1" in claimed  # no QA at all
    flagged = [s for s in data["statements"] if any(f["code"] == "no_qa_citation" for f in s["flags"])]
    assert flagged, "statements citing C1 without QA should be flagged deterministically"


def test_no_deploy_or_release_approval_endpoint_exists(client):
    paths = " ".join(client.get("/openapi.json").json()["paths"])
    assert "deploy" not in paths
    assert "/approve" not in paths


def test_analyze_blocked_when_package_invalid(client):
    rid = client.post("/api/releases", json={"name": "Empty"}).json()["id"]
    vid = client.post(f"/api/releases/{rid}/versions", json={"package": {}}).json()["id"]
    res = client.post(f"/api/versions/{vid}/analyze")
    assert res.status_code == 422
    assert res.json()["detail"]["errors"]


def test_guardrail_failure_is_retried_once_then_succeeds(client, sample, monkeypatch):
    llm = MockLLM()
    llm.fail_first_statements_with = StatementsOutput(statements=[StatementOut(audience="technical", section="summary", text="x", citations=["F99"])])
    patch_llm(monkeypatch, llm)
    res = client.post(f"/api/versions/{sample[1]}/analyze")
    assert res.status_code == 200
    assert ai_runs()[-2:] == [("statements", "guardrail_failed"), ("statements", "ok")]


def test_persistent_bad_output_gives_error_state_and_saves_nothing(client, sample, monkeypatch):
    class AlwaysBad(MockLLM):
        def _statements(self, package, gaps):
            return StatementsOutput(statements=[StatementOut(audience="client", section="summary", text="x", citations=["F99"])])

    patch_llm(monkeypatch, AlwaysBad())
    res = client.post(f"/api/versions/{sample[1]}/analyze")
    assert res.status_code == 502
    assert res.json()["detail"]["retryable"] is True
    detail = client.get(f"/api/versions/{sample[1]}").json()
    assert detail["statements"] == [] and detail["analysis"] is None


def test_provider_rate_limit_is_reported_clearly(client, sample, monkeypatch):
    class Limited(MockLLM):
        def generate(self, *a, **k):
            raise LLMError("rate_limit", "slow down")

    patch_llm(monkeypatch, Limited())
    res = client.post(f"/api/versions/{sample[1]}/analyze")
    assert res.status_code == 429
    assert res.json()["detail"]["kind"] == "rate_limit"


def test_rerun_with_approved_statements_needs_force(client, analyzed):
    _rid, vid, data = analyzed
    client.patch(f"/api/statements/{data['statements'][0]['id']}", json={"status": "approved"})
    assert client.post(f"/api/versions/{vid}/analyze").status_code == 409
    assert client.post(f"/api/versions/{vid}/analyze?force=true").status_code == 200


def test_analyze_endpoint_is_rate_limited(client, sample, monkeypatch):
    monkeypatch.setattr("app.services.ratelimit.get_settings", lambda: type("S", (), {"analyze_rate_limit_per_minute": 2})())
    codes = [client.post(f"/api/versions/{sample[1]}/analyze").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
