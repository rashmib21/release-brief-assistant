"""Problems found while preparing the deployment."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.config import Settings


@pytest.mark.parametrize(
    "url, expected",
    [
        ("postgres://u:p@host/db?sslmode=require", "postgresql+psycopg2://u:p@host/db?sslmode=require"),
        ("postgresql://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("sqlite:///./app.db", "sqlite:///./app.db"),
    ],
)
def test_database_url_names_the_psycopg2_driver(url, expected):
    # SQLAlchemy 2.1 defaults plain postgresql:// to psycopg v3, which is not installed.
    assert Settings(database_url=f"  {url} ").sqlalchemy_url == expected


def test_concurrent_analysis_conflict_is_409_not_500(client, sample, monkeypatch):
    _, vid = sample
    from app.routers import versions

    def boom(*a, **k):
        raise IntegrityError("insert", {}, Exception("duplicate key analyses_version_id_key"))

    monkeypatch.setattr(versions, "run_analysis", boom)
    res = client.post(f"/api/versions/{vid}/analyze")
    assert res.status_code == 409
    assert res.json()["detail"]["retryable"] is True


def test_control_characters_removed_from_ids(client, sample):
    rid, _ = sample
    res = client.post(f"/api/releases/{rid}/versions", json={"package": {"features": [{"id": "F\x007", "text": "x"}], "qa_summary": [{"text": "q", "covers": ["F\x007"]}]}})
    assert res.status_code == 201
    pkg = client.get(f"/api/versions/{res.json()['id']}").json()["package"]
    assert pkg["features"][0]["id"] == "F7"
    assert pkg["qa_summary"][0]["covers"] == ["F7"]
