import subprocess

import pytest
from fastapi.testclient import TestClient

from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    """A TestClient over a real git repo (plan writes commit, so git is required)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def _capture(client, title="Something"):
    return client.post("/api/capture", json={"title": title}).json()["id"]


def _today_ids(client):
    return [e["id"] for e in client.get("/api/today").json()["entries"]]


def test_add_to_today_is_idempotent(client):
    todo_id = _capture(client, "Plan me")
    assert client.post(f"/api/today/{todo_id}").status_code == 200
    assert client.post(f"/api/today/{todo_id}").status_code == 200  # again: no dup
    assert _today_ids(client) == [todo_id]


def test_add_unknown_todo_is_404(client):
    assert client.post("/api/today/nope").status_code == 404


def test_set_status_and_validation(client):
    todo_id = _capture(client)
    client.post(f"/api/today/{todo_id}")

    resp = client.patch(f"/api/today/{todo_id}", json={"status": "doing"})
    assert resp.status_code == 200
    entry = next(e for e in resp.json()["entries"] if e["id"] == todo_id)
    assert entry["status"] == "doing"

    assert (
        client.patch(f"/api/today/{todo_id}", json={"status": "bogus"}).status_code
        == 400
    )
    assert client.patch("/api/today/nope", json={"status": "doing"}).status_code == 404


def test_remove_from_today(client):
    todo_id = _capture(client)
    client.post(f"/api/today/{todo_id}")
    assert client.delete(f"/api/today/{todo_id}").status_code == 204
    assert _today_ids(client) == []
    assert client.delete(f"/api/today/{todo_id}").status_code == 404  # gone now


def test_completing_a_planned_todo_ticks_the_entry(client):
    todo_id = _capture(client, "Do and tick")
    client.post(f"/api/today/{todo_id}")
    client.post(f"/api/todos/{todo_id}/complete")
    entry = next(
        e for e in client.get("/api/today").json()["entries"] if e["id"] == todo_id
    )
    assert entry["status"] == "done"


def test_history_lists_completed_todos(client):
    first = _capture(client, "First done")
    second = _capture(client, "Second done")
    client.post(f"/api/todos/{first}/complete")
    client.post(f"/api/todos/{second}/complete")

    done = client.get("/api/done").json()
    titles = {t["title"] for t in done}
    assert titles == {"First done", "Second done"}
    assert all(t["state"] == "done" and t["completed"] for t in done)


def test_plan_write_makes_a_git_commit(client, tmp_path):
    todo_id = _capture(client, "Committed plan")
    client.post(f"/api/today/{todo_id}")
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "plan: add Committed plan" in log.stdout
