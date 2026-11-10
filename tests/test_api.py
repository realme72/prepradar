"""API smoke tests against the local database (skipped if Postgres has no data)."""
import pytest
from fastapi.testclient import TestClient

from prepradar.api import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def needs_data():
    try:
        if not client.get("/api/companies").json():
            pytest.skip("no companies ingested")
    except Exception as e:
        pytest.skip(f"database unavailable: {e}")


def test_companies_lists_ingested():
    names = [c["company"] for c in client.get("/api/companies").json()]
    assert "zemoso" in names


def test_questions_have_sources():
    rows = client.get("/api/companies/zemoso/questions", params={"track": "Backend"}).json()
    assert rows and all(r["urls"] for r in rows)


def test_unknown_company_is_404():
    assert client.get("/api/companies/nope-inc/questions").status_code == 404


def test_search_ranks_by_meaning():
    rows = client.get("/api/companies/zemoso/search", params={"q": "sql joins", "k": 3}).json()
    assert rows[0]["category"] == "Database"
