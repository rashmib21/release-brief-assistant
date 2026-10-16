#!/usr/bin/env python3
"""End-to-end smoke test on the built-in sample release. Standard library only.

Usage:
    python scripts/smoke_test.py                              # local server on :8000
    python scripts/smoke_test.py --base-url https://your-app.onrender.com

It walks the whole workflow through the public API: section check, AI analysis, guardrail
properties, review gating, stale detection on a new version, compare, and the final brief.
Checks marked FAIL mean the app is broken. Checks marked WARN are AI-quality observations
(a real model may phrase things differently) that a person should look at.

Note: this creates a new sample release in whatever database the server uses.
"""
import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"{status:5} {name}" + (f"  ({detail})" if detail else ""))


def check(cond: bool, name: str, detail: str = "") -> bool:
    record("PASS" if cond else "FAIL", name, "" if cond else detail)
    return cond


def warn_unless(cond: bool, name: str, detail: str = "") -> None:
    record("PASS" if cond else "WARN", name, "" if cond else detail)


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, timeout=150):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/api{path}", data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or "null")
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw.decode(errors="replace")[:300]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()
    api = Api(args.base_url)

    # 1. health
    try:
        code, health = api.call("GET", "/health", timeout=60)  # first hit may wake a sleeping free-tier host
    except Exception as e:
        print(f"Cannot reach {args.base_url}: {e}")
        return 2
    check(code == 200, "health endpoint answers", str(health))
    print(f"      LLM provider on the server: {health.get('llm_provider') if isinstance(health, dict) else '?'}")

    # 2. sample release + deterministic check
    code, rel = api.call("POST", "/releases/sample")
    if not check(code == 201, "sample release loads", str(rel)):
        return 1
    rid, vid = rel["id"], rel["version_id"]
    code, val = api.call("POST", f"/versions/{vid}/validate")
    check(code == 200 and val["valid"], "section check passes on the sample")

    code, bad_rel = api.call("POST", "/releases", {"name": "Empty package"})
    code, bad_v = api.call("POST", f"/releases/{bad_rel['id']}/versions", {"package": {}})
    code, blocked = api.call("POST", f"/versions/{bad_v['id']}/analyze")
    check(code == 422, "analysis is blocked when sections are blank", f"HTTP {code}")

    # 3. AI analysis
    started = time.time()
    code, d = api.call("POST", f"/versions/{vid}/analyze")
    secs = time.time() - started
    if not check(code == 200, "AI analysis succeeds", f"HTTP {code}: {json.dumps(d)[:300]}"):
        return 1
    print(f"      analysis took {secs:.1f}s")
    stmts = d["statements"]
    check(len(stmts) > 0, "statements were produced", f"{len(stmts)}")
    check({s["status"] for s in stmts} == {"draft"}, "AI output is saved as draft only (never approved)")
    check(all(s["citations"] and all(c["exists"] for c in s["citations"]) for s in stmts), "every statement cites existing items")
    for aud in ("technical", "client"):
        check(any(s["audience"] == aud and s["section"] == "summary" for s in stmts), f"{aud} summary present")
        check(any(s["audience"] == aud and s["section"] == "risks" for s in stmts), f"{aud} risks and limitations present")
    check(d["review_state"] == "in_review", "version moves to in_review (not approved)")

    # 4. AI quality observations (WARN only)
    a = d["analysis"]
    claimed = {u["claim_item_id"] for u in a["unsupported_claims"]}
    warn_unless("F2" in claimed, "AI flagged 'dark mode works on all devices' (QA covered Android only)", f"flagged: {sorted(claimed)}")
    warn_unless("C1" in claimed or any(m for m in a["missing_info"] if "C1" in m["related_ids"]), "AI noticed the cancellation-window change has no QA evidence")
    warn_unless(any("rollback" in (m["topic"] + m["why_it_matters"]).lower() for m in a["missing_info"]), "AI noticed migration 042 has no rollback steps")
    impact = {c["item_id"]: c["impact"] for c in a["classifications"]}
    warn_unless(impact.get("C1") == "high", "cancellation-window change rated high impact", f"got {impact.get('C1')}")
    warn_unless(impact.get("F2") in ("low", "medium"), "dark mode not rated high impact", f"got {impact.get('F2')}")
    client_text = " ".join(s["effective_text"] for s in stmts if s["audience"] == "client")
    warn_unless("migration 042" not in client_text.lower() and "autopay_mandates" not in client_text, "client statements avoid internal migration details")
    print("      classification:", impact)

    # 5. review gating
    code, r = api.call("POST", f"/versions/{vid}/final-brief")
    check(code == 409, "final brief is blocked while statements are unreviewed", f"HTTP {code}")
    code, r = api.call("PATCH", f"/statements/{stmts[0]['id']}", {"status": "stale"})
    check(code == 422, "users cannot set a statement to stale by hand", f"HTTP {code}")
    code, r = api.call("PATCH", f"/statements/{stmts[0]['id']}", {"citations": ["F99"]})
    check(code == 422, "fake citation is rejected on edit", f"HTTP {code}")
    code, r = api.call("PATCH", f"/statements/{stmts[0]['id']}", {"edited_text": "Reworded by a person."})
    check(code == 200 and r["effective_text"] == "Reworded by a person." and r["text"] == stmts[0]["text"], "edit keeps the original AI text")

    # approve all except the first one, which we reject
    for i, s in enumerate(stmts):
        code, r = api.call("PATCH", f"/statements/{s['id']}", {"status": "rejected" if i == 0 else "approved"})
        if code != 200:
            check(False, "approve/reject works", f"HTTP {code}")
            break
    else:
        record("PASS", "approve and reject work")

    # 6. new version => stale statements
    code, v1 = api.call("GET", f"/versions/{vid}")
    pkg = copy.deepcopy(v1["package"])
    pkg["features"][0]["text"] = "UPI autopay for weekly and monthly orders."
    code, v2s = api.call("POST", f"/releases/{rid}/versions", {"package": pkg})
    check(code == 201, "new version saves", f"HTTP {code}")
    code, v2 = api.call("GET", f"/versions/{v2s['id']}")
    stale = [s for s in v2["statements"] if s["status"] == "stale"]
    check(len(stale) > 0 and all(any(c["id"] == "F1" for c in s["citations"]) for s in stale), "statements citing the changed item became stale", f"{len(stale)} stale")
    check(all("F1" in (s["stale_reason"] or "") for s in stale), "stale statements say why")
    still_ok = [s for s in v2["statements"] if s["status"] == "approved"]
    check(len(still_ok) > 0, "unrelated approvals survive the new version")
    code, r = api.call("POST", f"/versions/{v2s['id']}/final-brief")
    check(code == 409, "stale statements block the final brief on the new version", f"HTTP {code}")
    code, v1_again = api.call("GET", f"/versions/{vid}")
    check(v1_again["package"] == v1["package"] and "stale" not in {s["status"] for s in v1_again["statements"]}, "version 1 is unchanged by version 2")

    # 7. compare
    code, cmp = api.call("GET", f"/releases/{rid}/compare?from=1&to=2")
    check(code == 200 and cmp["diff"]["totals"]["changed"] == 1, "compare shows one changed item", json.dumps(cmp.get("diff", {}).get("totals")))
    check(len(cmp["stale_statements"]) == len(stale), "compare lists the same stale statements")

    # 8. final brief on version 1
    code, brief = api.call("POST", f"/versions/{vid}/final-brief")
    check(code == 201, "final brief generates once everything is reviewed", f"HTTP {code}: {json.dumps(brief)[:200]}")
    if code == 201:
        md = brief["content_md"]
        check("NOT a release approval" in md, "brief states it is not a release approval")
        check(stmts[0]["text"] not in md and stmts[0]["effective_text"] not in md, "rejected statement is not in the brief")
        check(md.count("[") >= 5, "brief keeps citations")
        code, locked = api.call("PATCH", f"/statements/{stmts[1]['id']}", {"status": "draft"})
        check(code == 409, "version is locked after the brief", f"HTTP {code}")

    # summary
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\n{len(results) - len(fails) - len(warns)} passed, {len(warns)} warnings, {len(fails)} failed")
    if warns:
        print("Warnings are AI-quality observations. Open the app and read the analysis yourself.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
