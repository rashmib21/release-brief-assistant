"""Inputs and provider problems that used to cause unexpected 500 errors."""
import pytest

from app.llm import client as llm_client
from app.llm.client import GeminiClient, LLMError
from app.schemas import ClassificationItem, ClassificationOutput, StatementOut, StatementsOutput
from app.services import guardrails

BIG = 99999999999999999999


@pytest.mark.parametrize("path", [f"/api/releases/{BIG}", f"/api/versions/{BIG}", f"/api/releases/{BIG}/versions", "/api/releases/0", "/api/versions/-5"])
def test_out_of_range_ids_are_404_not_500(client, path):
    assert client.get(path).status_code == 404


def test_patching_huge_statement_id_is_404(client):
    assert client.patch(f"/api/statements/{BIG}", json={"status": "approved"}).status_code == 404


def test_blank_release_name_rejected(client):
    assert client.post("/api/releases", json={"name": "   "}).status_code == 422


def test_release_name_is_cleaned(client):
    res = client.post("/api/releases", json={"name": "  App\x00  2.3 "})
    assert res.status_code == 201 and res.json()["name"] == "App 2.3"


def test_nul_bytes_removed_from_package_text(client, sample):
    rid, _ = sample
    res = client.post(f"/api/releases/{rid}/versions", json={"package": {"features": [{"text": "bad\x00text"}]}})
    assert res.status_code == 201
    pkg = client.get(f"/api/versions/{res.json()['id']}").json()["package"]
    assert pkg["features"][0]["text"] == "badtext"


def test_oversized_item_text_rejected(client, sample):
    rid, _ = sample
    res = client.post(f"/api/releases/{rid}/versions", json={"package": {"features": [{"text": "x" * 5000}]}})
    assert res.status_code == 422


def test_too_many_items_rejected(client, sample):
    rid, _ = sample
    res = client.post(f"/api/releases/{rid}/versions", json={"package": {"features": [{"text": "a"}] * 60}})
    assert res.status_code == 422


def test_unknown_api_path_is_json_404(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404


def test_normalize_fixes_case_and_duplicates():
    out = ClassificationOutput(classifications=[ClassificationItem(item_id=" f1 ", user_groups=[], impact="High ", reason="r")])
    guardrails.normalize_output(out)
    assert out.classifications[0].item_id == "F1" and out.classifications[0].impact == "high"

    st = StatementsOutput(statements=[StatementOut(audience="Client", section="RISKS", text="t", citations=["f1", "F1", " q1"])])
    guardrails.normalize_output(st)
    assert st.statements[0].audience == "client" and st.statements[0].section == "risks"
    assert st.statements[0].citations == ["F1", "Q1"]


class _Flaky(GeminiClient):
    """GeminiClient whose provider call fails a set number of times, without any network."""

    def __init__(self, failures: list[LLMError]):
        super().__init__("fake-key", "gemini-2.5-flash", 5, max_retries=2)
        self.failures, self.calls = failures, 0

    def _call_once(self, system, user, schema):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"


def test_gemini_retries_temporary_errors(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    c = _Flaky([LLMError("unavailable", "busy"), LLMError("rate_limit", "slow")])
    assert c.generate("classify", "s", "u", ClassificationOutput, {}) == "ok"
    assert c.calls == 3


def test_gemini_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    c = _Flaky([LLMError("unavailable", "busy")] * 5)
    with pytest.raises(LLMError) as err:
        c.generate("classify", "s", "u", ClassificationOutput, {})
    assert err.value.kind == "unavailable" and c.calls == 3


def test_gemini_does_not_retry_bad_key(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    c = _Flaky([LLMError("not_configured", "bad key")])
    with pytest.raises(LLMError):
        c.generate("classify", "s", "u", ClassificationOutput, {})
    assert c.calls == 1


def test_provider_outage_returns_503_with_retry_flag(client, sample, monkeypatch):
    _, vid = sample

    class Down:
        model_name = "down"

        def generate(self, *a, **k):
            raise LLMError("unavailable", "overloaded")

    from app.routers import versions

    monkeypatch.setattr(versions, "get_llm_client", lambda: Down())
    res = client.post(f"/api/versions/{vid}/analyze")
    assert res.status_code == 503
    assert res.json()["detail"]["retryable"] is True
    # nothing half-saved
    assert client.get(f"/api/versions/{vid}").json()["statements"] == []
