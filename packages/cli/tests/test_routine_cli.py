import subprocess
from datetime import date

import pytest
from typer.testing import CliRunner

from neverland.cli import main as cli
from neverland.core import store
from neverland.core.vocabulary import RepoConfig, save_repo_config

runner = CliRunner()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git data repo wired as the CLI's active one, with network sync off."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    save_repo_config(tmp_path, RepoConfig(sync_auto=False))
    for var, val in {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(var, val)
    monkeypatch.setattr(cli, "require_data_dir", lambda: tmp_path)
    return tmp_path


def _answers(monkeypatch, *, choices, texts):
    """Feed canned answers to the fzf/gum prompts, in order."""
    picks, lines = list(choices), list(texts)
    monkeypatch.setattr(cli.prompt, "choose", lambda *a, **k: picks.pop(0))
    monkeypatch.setattr(cli.prompt, "text_input", lambda *a, **k: lines.pop(0))


def test_routine_add_days(repo, monkeypatch):
    _answers(
        monkeypatch,
        choices=["every N days", "(none)", "(none)"],  # freq, context, area
        texts=["3", "0"],  # interval, lead
    )
    result = runner.invoke(cli.app, ["routine", "add", "Water the plants"])
    assert result.exit_code == 0, result.output

    routines = store.list_routines(repo)
    assert len(routines) == 1
    assert routines[0].title == "Water the plants"
    assert routines[0].recurrence.describe() == "every 3 days"


def test_routine_add_weekly_with_context(repo, monkeypatch):
    _answers(
        monkeypatch,
        choices=["weekly (given weekdays)", "@home", "home"],
        texts=["mon,wed,sat", "0"],
    )
    assert runner.invoke(cli.app, ["routine", "add", "Run"]).exit_code == 0

    routine = store.list_routines(repo)[0]
    assert routine.recurrence.describe() == "weekly: Mon, Wed, Sat"
    assert (routine.context, routine.area) == ("@home", "home")


def test_routine_list_and_pause(repo, monkeypatch):
    _answers(
        monkeypatch, choices=["every N days", "(none)", "(none)"], texts=["1", "0"]
    )
    runner.invoke(cli.app, ["routine", "add", "Daily thing"])

    listed = runner.invoke(cli.app, ["routine"])
    assert "Daily thing" in listed.output and "every day" in listed.output

    monkeypatch.setattr(
        cli.prompt, "choose", lambda *a, **k: "Daily thing  (every day)"
    )
    assert runner.invoke(cli.app, ["routine", "pause"]).exit_code == 0
    assert store.list_routines(repo)[0].active is False


def test_root_materializes_due_routines(repo, monkeypatch):
    _answers(
        monkeypatch, choices=["every N days", "(none)", "(none)"], texts=["1", "0"]
    )
    runner.invoke(cli.app, ["routine", "add", "Water"])
    # the add already materialized it; it must be a real todo in today's plan
    assert [t.title for t in store.list_active(repo)] == ["Water"]
    plan = store.load_day_plan(repo, date.today())
    assert [e.title for e in plan.entries] == ["Water"]

    # looking at today again must not duplicate it
    assert runner.invoke(cli.app, []).exit_code == 0
    assert len(store.list_active(repo)) == 1


def test_routine_rm(repo, monkeypatch):
    _answers(
        monkeypatch, choices=["every N days", "(none)", "(none)"], texts=["5", "0"]
    )
    runner.invoke(cli.app, ["routine", "add", "Gone soon"])

    monkeypatch.setattr(
        cli.prompt, "choose", lambda *a, **k: "Gone soon  (every 5 days)"
    )
    monkeypatch.setattr(cli.prompt, "confirm", lambda *a, **k: True)
    assert runner.invoke(cli.app, ["routine", "rm"]).exit_code == 0
    assert store.list_routines(repo) == []
