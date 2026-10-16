import copy


def new_version(client, rid, vid, mutate):
    pkg = copy.deepcopy(client.get(f"/api/versions/{vid}").json()["package"])
    mutate(pkg)
    res = client.post(f"/api/releases/{rid}/versions", json={"package": pkg})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def by_status(data):
    out = {}
    for s in data["statements"]:
        out.setdefault(s["status"], []).append(s)
    return out


def approve_everything(client, data):
    for s in data["statements"]:
        client.patch(f"/api/statements/{s['id']}", json={"status": "approved"})


def test_package_is_immutable_once_analysed(client, analyzed):
    _rid, vid, _ = analyzed
    pkg = client.get(f"/api/versions/{vid}").json()["package"]
    assert client.put(f"/api/versions/{vid}/package", json=pkg).status_code == 409


def test_package_can_be_fixed_before_analysis(client, sample):
    _rid, vid = sample
    pkg = client.get(f"/api/versions/{vid}").json()["package"]
    pkg["features"][0]["text"] = "UPI autopay for weekly orders."
    assert client.put(f"/api/versions/{vid}/package", json=pkg).status_code == 200


def test_changed_item_makes_only_the_statements_citing_it_stale(client, analyzed):
    rid, vid, data = analyzed
    approve_everything(client, data)
    v2 = new_version(client, rid, vid, lambda p: p["features"][0].update(text="UPI autopay for weekly orders only."))
    d2 = client.get(f"/api/versions/{v2}").json()
    groups = by_status(d2)
    assert groups["stale"], "statements citing F1 should be stale"
    assert groups["approved"], "unrelated approvals must survive"
    for s in groups["stale"]:
        assert "F1 changed" in s["stale_reason"]
        assert any(c["id"] == "F1" for c in s["citations"])
    assert all(s["carried_from_id"] for s in d2["statements"])
    # v1 itself is untouched
    assert set(by_status(client.get(f"/api/versions/{vid}").json())) == {"approved"}


def test_removed_item_marks_statements_stale_and_blocks_approval(client, analyzed):
    rid, vid, data = analyzed
    approve_everything(client, data)
    v2 = new_version(client, rid, vid, lambda p: p.update(bug_fixes=[{"id": "B2", "text": "None"}]))
    d2 = client.get(f"/api/versions/{v2}").json()
    stale = [s for s in d2["statements"] if s["status"] == "stale" and "B1 was removed" in s["stale_reason"]]
    assert stale
    res = client.patch(f"/api/statements/{stale[0]['id']}", json={"status": "approved"})
    assert res.status_code == 422
    # reject resolves it
    assert client.patch(f"/api/statements/{stale[0]['id']}", json={"status": "rejected"}).status_code == 200


def test_approving_a_stale_statement_refreshes_it_and_unblocks_the_brief(client, analyzed):
    rid, vid, data = analyzed
    approve_everything(client, data)
    v2 = new_version(client, rid, vid, lambda p: p["features"][0].update(text="UPI autopay for weekly orders only."))
    d2 = client.get(f"/api/versions/{v2}").json()
    assert client.post(f"/api/versions/{v2}/final-brief").status_code == 409  # stale blocks the brief
    for s in by_status(d2)["stale"]:
        assert client.patch(f"/api/statements/{s['id']}", json={"status": "approved"}).json()["status"] == "approved"
    assert client.post(f"/api/versions/{v2}/final-brief").status_code == 201


def test_compare_reports_added_removed_changed_and_stale(client, analyzed):
    rid, vid, data = analyzed

    def mutate(p):
        p["features"][0]["text"] = "UPI autopay for weekly orders."  # changed
        p["bug_fixes"] = [{"id": "B2", "text": "Fixed a login timeout."}]  # B1 removed, B2 added

    new_version(client, rid, vid, mutate)
    res = client.get(f"/api/releases/{rid}/compare", params={"from": 1, "to": 2}).json()
    sections = res["diff"]["sections"]
    assert [c["id"] for c in sections["features"]["changed"]] == ["F1"]
    assert [i["id"] for i in sections["bug_fixes"]["added"]] == ["B2"]
    assert [i["id"] for i in sections["bug_fixes"]["removed"]] == ["B1"]
    assert res["diff"]["totals"] == {"added": 1, "removed": 1, "changed": 1}
    reasons = " ".join(s["reason"] for s in res["stale_statements"])
    assert "F1 changed" in reasons and "B1 was removed" in reasons
    assert client.get(f"/api/releases/{rid}/compare", params={"from": 1, "to": 9}).status_code == 404


def test_identical_package_creates_no_stale_statements(client, analyzed):
    rid, vid, _ = analyzed
    v2 = new_version(client, rid, vid, lambda p: None)
    assert "stale" not in by_status(client.get(f"/api/versions/{v2}").json())


def test_compare_and_new_version_agree_on_stale_and_ignore_rejected(client, analyzed):
    rid, vid, data = analyzed
    approve_everything(client, data)
    f1 = next(s for s in data["statements"] if any(c["id"] == "F1" for c in s["citations"]))
    client.patch(f"/api/statements/{f1['id']}", json={"status": "rejected"})
    v2 = new_version(client, rid, vid, lambda p: p["features"][0].update(text="UPI autopay for weekly orders only."))
    stale_on_version = {s["text"] for s in client.get(f"/api/versions/{v2}").json()["statements"] if s["status"] == "stale"}
    cmp = client.get(f"/api/releases/{rid}/compare", params={"from": 1, "to": 2}).json()
    assert f1["text"] not in {s["text"] for s in cmp["stale_statements"]}
    assert {s["text"] for s in cmp["stale_statements"]} == stale_on_version
