import subprocess

import pytest
from fastapi.testclient import TestClient

from neverland.core import store
from neverland.core.todo import TodoState
from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    """A TestClient over a real git repo (mutations commit, so git is required)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def _capture(client, title="Something"):
    """Capture a todo and return its id."""
    return client.post("/api/capture", json={"title": title}).json()["id"]


def test_clarify_sets_state_context_area(client, tmp_path):
    todo_id = _capture(client, "Call the plumber")
    resp = client.patch(
        f"/api/todos/{todo_id}",
        json={"state": "next", "context": "@phone", "area": "home"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["state"], body["context"], body["area"]) == ("next", "@phone", "home")

    # persisted, still active (a state change never archives the file)
    stored = store.find_active(tmp_path, todo_id)
    assert stored.state is TodoState.NEXT
    assert stored.context == "@phone"


def test_clarify_rename_and_partial_patch(client, tmp_path):
    todo_id = _capture(client, "buy milk")
    # only the title is sent: state stays inbox
    resp = client.patch(f"/api/todos/{todo_id}", json={"title": "Buy oat milk"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Buy oat milk"
    assert store.find_active(tmp_path, todo_id).state is TodoState.INBOX


def test_clarify_rejects_unknown_vocabulary(client):
    todo_id = _capture(client)
    assert (
        client.patch(f"/api/todos/{todo_id}", json={"area": "nope"}).status_code == 400
    )
    assert (
        client.patch(f"/api/todos/{todo_id}", json={"context": "@nope"}).status_code
        == 400
    )
    assert (
        client.patch(f"/api/todos/{todo_id}", json={"state": "bogus"}).status_code
        == 400
    )


def test_patch_state_done_archives(client, tmp_path):
    todo_id = _capture(client, "Finish this")
    resp = client.patch(f"/api/todos/{todo_id}", json={"state": "done"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "done"
    assert store.find_active(tmp_path, todo_id) is None
    assert [t.id for t in store.list_done(tmp_path)] == [todo_id]


def test_complete_endpoint_archives(client, tmp_path):
    todo_id = _capture(client, "Wash the car")
    resp = client.post(f"/api/todos/{todo_id}/complete")
    assert resp.status_code == 200
    assert store.find_active(tmp_path, todo_id) is None
    assert [t.id for t in store.list_done(tmp_path)] == [todo_id]


def test_delete_endpoint_removes(client, tmp_path):
    todo_id = _capture(client, "Never mind")
    resp = client.delete(f"/api/todos/{todo_id}")
    assert resp.status_code == 204
    assert store.find_active(tmp_path, todo_id) is None
    assert store.list_done(tmp_path) == []


def test_missing_todo_is_404(client):
    assert client.patch("/api/todos/nope", json={"state": "next"}).status_code == 404
    assert client.post("/api/todos/nope/complete").status_code == 404
    assert client.delete("/api/todos/nope").status_code == 404


def test_mutation_makes_a_git_commit(client, tmp_path):
    todo_id = _capture(client, "Track edit")
    client.patch(f"/api/todos/{todo_id}", json={"state": "someday"})
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "edit: Track edit" in log.stdout
