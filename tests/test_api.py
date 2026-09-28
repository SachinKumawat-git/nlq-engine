import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.routes.query as query_route


class FakeLLM:
    def complete_json(self, system, user):
        return {
            "answerable": True,
            "sql": "SELECT COUNT(*) AS n FROM dataset",
            "reasoning": "count rows",
            "refusal_reason": None,
        }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(query_route, "get_llm_client", lambda: FakeLLM())
    return TestClient(app)


def _wait_for_job(client, job_id, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.1)
    raise TimeoutError("job did not complete in time")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ingest_rejects_non_csv(client):
    r = client.post("/ingest", files={"file": ("data.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400


def test_full_ingest_and_query_flow(client):
    csv_bytes = b"id,item,qty,price\n1,Widget,2,9.99\n2,Gadget,1,19.99\n"
    r = client.post("/ingest", files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["status"] == "done"
    dataset_id = job["result"]["dataset_id"]
    assert job["result"]["row_count"] == 2

    r2 = client.get(f"/datasets/{dataset_id}")
    assert r2.status_code == 200
    assert r2.json()["row_count"] == 2

    r3 = client.post("/query", json={"dataset_id": dataset_id, "question": "how many rows?"})
    assert r3.status_code == 202
    qjob = _wait_for_job(client, r3.json()["job_id"])
    assert qjob["status"] == "done"
    assert qjob["result"]["answerable"] is True
    assert qjob["result"]["rows"] == [[2]]


def test_query_unknown_dataset_returns_404(client):
    r = client.post("/query", json={"dataset_id": "nope", "question": "hi"})
    assert r.status_code == 404


def test_job_unknown_id_returns_404(client):
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404


def test_no_stack_trace_leaks_on_unexpected_error(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated internal failure with a fake /secret/path")

    monkeypatch.setattr("app.routes.datasets.load_profile", boom)
    r = client.get("/datasets/anything")
    assert r.status_code == 500
    assert "secret" not in r.text
    assert "Traceback" not in r.text
