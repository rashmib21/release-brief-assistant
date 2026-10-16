def approve_all(client, data, reject_ids=()):
    for s in data["statements"]:
        status = "rejected" if s["id"] in reject_ids else "approved"
        assert client.patch(f"/api/statements/{s['id']}", json={"status": status}).status_code == 200


def test_user_can_edit_approve_and_reject(client, analyzed):
    _rid, _vid, data = analyzed
    a, b, c = data["statements"][:3]
    r = client.patch(f"/api/statements/{a['id']}", json={"edited_text": "Reworded by a human."}).json()
    assert r["effective_text"] == "Reworded by a human." and r["text"] == a["text"]
    assert client.patch(f"/api/statements/{a['id']}", json={"status": "approved"}).json()["status"] == "approved"
    assert client.patch(f"/api/statements/{b['id']}", json={"status": "rejected"}).json()["status"] == "rejected"
    # editing an approved statement sends it back to draft: it needs a fresh approval
    r = client.patch(f"/api/statements/{a['id']}", json={"edited_text": "Reworded again."}).json()
    assert r["status"] == "draft"


def test_status_values_and_citations_are_validated(client, analyzed):
    sid = analyzed[2]["statements"][0]["id"]
    assert client.patch(f"/api/statements/{sid}", json={"status": "stale"}).status_code == 422
    assert client.patch(f"/api/statements/{sid}", json={"edited_text": "  "}).status_code == 422
    assert client.patch(f"/api/statements/{sid}", json={"citations": ["F99"]}).status_code == 422
    assert client.patch(f"/api/statements/{sid}", json={"citations": []}).status_code == 422


def test_final_brief_blocked_until_every_statement_is_reviewed(client, analyzed):
    _rid, vid, data = analyzed
    res = client.post(f"/api/versions/{vid}/final-brief")
    assert res.status_code == 409
    assert len(res.json()["detail"]["blocking_statement_ids"]) == len(data["statements"])


def test_final_brief_contains_only_approved_text_and_locks_version(client, analyzed):
    _rid, vid, data = analyzed
    rejected = data["statements"][0]
    approve_all(client, data, reject_ids={rejected["id"]})
    res = client.post(f"/api/versions/{vid}/final-brief")
    assert res.status_code == 201
    md = res.json()["content_md"]
    assert "NOT a release approval" in md
    assert rejected["text"] not in md
    assert "Open flags from analysis" in md
    assert client.get(f"/api/versions/{vid}").json()["review_state"] == "brief_generated"
    # locked: no more edits, no second brief, no re-analysis
    assert client.patch(f"/api/statements/{data['statements'][1]['id']}", json={"status": "draft"}).status_code == 409
    assert client.post(f"/api/versions/{vid}/final-brief").status_code == 409
    assert client.post(f"/api/versions/{vid}/analyze").status_code == 409


def test_final_brief_needs_at_least_one_approved_statement(client, analyzed):
    _rid, vid, data = analyzed
    approve_all(client, data, reject_ids={s["id"] for s in data["statements"]})
    assert client.post(f"/api/versions/{vid}/final-brief").status_code == 409
