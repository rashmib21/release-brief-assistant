"""An older database file (missing newer columns) must be upgraded on startup instead of causing 500 errors."""
from sqlalchemy import inspect, text

from app.db import add_missing_columns, engine


def test_missing_columns_are_added(client):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE statements DROP COLUMN flags_json"))
        conn.execute(text("ALTER TABLE ai_runs DROP COLUMN request_id"))
    added = add_missing_columns()
    assert {"statements.flags_json", "ai_runs.request_id"} <= set(added)
    cols = {c["name"] for c in inspect(engine).get_columns("statements")}
    assert "flags_json" in cols
    assert add_missing_columns() == []  # nothing left to add


def test_full_flow_works_after_upgrade(client):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE statements DROP COLUMN stale_reason"))
    add_missing_columns()
    r = client.post("/api/releases/sample").json()
    assert client.post(f"/api/versions/{r['version_id']}/analyze").status_code == 200


def test_brief_can_be_generated_after_leftover_row(client, analyzed):
    _, vid, data = analyzed
    for s in data["statements"]:
        client.patch(f"/api/statements/{s['id']}", json={"status": "approved"})
    assert client.post(f"/api/versions/{vid}/final-brief").status_code == 201
    assert client.post(f"/api/versions/{vid}/final-brief").status_code == 409  # locked, not a crash
