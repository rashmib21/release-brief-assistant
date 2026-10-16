import os
import tempfile

# Must be set before the app is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.services import ratelimit


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample(client):
    """A release with v1 loaded from the sample package. Returns (release_id, version_id)."""
    r = client.post("/api/releases/sample").json()
    return r["id"], r["version_id"]


@pytest.fixture()
def analyzed(client, sample):
    rid, vid = sample
    res = client.post(f"/api/versions/{vid}/analyze")
    assert res.status_code == 200, res.text
    return rid, vid, res.json()
