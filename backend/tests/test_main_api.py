from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.repository import Repository


def test_api_saves_data_source_and_creates_run_from_it(tmp_path: Path, monkeypatch):
    test_repo = Repository(tmp_path / "app.sqlite3")
    test_repo.init()
    monkeypatch.setattr(main, "repo", test_repo)

    calls = []

    def fake_run_generation(*args):
        calls.append(args)

    monkeypatch.setattr(main, "run_generation", fake_run_generation)
    client = TestClient(main.app)

    created = client.post(
        "/api/data-sources",
        json={
            "name": "Sales CRM",
            "connection": {
                "host": "127.0.0.1",
                "port": 3306,
                "user": "readonly",
                "password": "secret",
                "database": "crm",
                "connect_timeout": 10,
            },
            "knowledge_base": "expected_amount means forecast contract value",
        },
    )

    assert created.status_code == 200
    data_source_id = created.json()["id"]

    run_response = client.post(
        "/api/runs",
        json={
            "name": "Saved source run",
            "data_source_id": data_source_id,
            "business_context": "Generate sales questions.",
            "question_count": 2,
            "sample_rows": 1,
        },
    )

    assert run_response.status_code == 200
    run = test_repo.get_run(run_response.json()["run_id"])
    assert run["data_source_id"] == data_source_id
    assert run["knowledge_base"] == "expected_amount means forecast contract value"
    assert calls[0][3].database == "crm"
    assert calls[0][-1] == "expected_amount means forecast contract value"
