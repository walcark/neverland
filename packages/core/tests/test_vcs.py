from neverland.core import store, vcs
from neverland.core.store import DONE_DIRNAME, TODOS_DIRNAME
from neverland.core.vocabulary import REPO_CONFIG_NAME


def test_setup_new_repo_scaffolds(tmp_path):
    target = tmp_path / "data"
    result = vcs.setup_repo(str(target))
    assert result.created_repo is True
    assert vcs.is_git_repo(target)
    assert vcs.is_todo_repo(target)
    assert (target / REPO_CONFIG_NAME).exists()
    assert (target / TODOS_DIRNAME).is_dir()
    assert (target / DONE_DIRNAME).is_dir()


def test_missing_layout_detection(tmp_path):
    assert set(vcs.missing_layout(tmp_path)) == {
        REPO_CONFIG_NAME,
        f"{TODOS_DIRNAME}/",
        f"{DONE_DIRNAME}/",
    }


def test_setup_adopts_existing_valid_repo(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))  # first time: scaffold
    result = vcs.setup_repo(str(target))  # second time: adoption
    assert result.adopted is True
    assert result.created_items == []


def test_setup_confirm_declined_on_unrelated_content(tmp_path):
    target = tmp_path / "data"
    target.mkdir()
    (target / "other.txt").write_text("unrelated content", encoding="utf-8")
    try:
        vcs.setup_repo(str(target), confirm=lambda _: False)
        raise AssertionError("should have raised RepoError")
    except vcs.RepoError:
        pass


def test_sync_commits_without_origin(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    store.create_todo(target, title="Task")
    result = vcs.sync(target)
    assert result.committed is True
    assert result.pushed is False
    assert result.warnings == []  # no origin -> no network warning


def test_sync_pushes_to_origin(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    store.create_todo(target, title="Task")
    result = vcs.sync(target)
    assert result.committed is True
    assert result.pushed is True

    files = vcs.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert any(
        line.startswith("todos/") and line.endswith(".md")
        for line in files.splitlines()
    )


def test_background_flush_drains_all_commits(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    # Several unpushed local commits (as after quick successive `add`s).
    for i in range(3):
        store.create_todo(target, title=f"Task {i}")
        vcs.sync(target, network=False)  # local commit only

    assert vcs._unpushed_count(target) == 0  # no upstream yet -> 0

    vcs.background_flush(target, window=0)

    # Everything is pushed, nothing left pending.
    assert vcs._unpushed_count(target) == 0
    files = vcs.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert files.count(".md") >= 3


def test_sync_lock_is_exclusive(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    with vcs.sync_lock(target) as first:
        assert first is True
        with vcs.sync_lock(target) as second:
            assert second is False  # already held -> non-blocking yields False
    # Once released, it can be re-acquired.
    with vcs.sync_lock(target) as again:
        assert again is True


# --- commit batching ---------------------------------------------------------


def _commit_count(target):
    return int(vcs.run_git(["rev-list", "--count", "HEAD"], cwd=target).stdout.strip())


def _head_message(target):
    return vcs.run_git(["log", "-1", "--format=%B"], cwd=target).stdout


def test_window_folds_consecutive_mutations_into_one_commit(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    before = _commit_count(target)

    for i in range(3):
        store.create_todo(target, title=f"Task {i}")
        assert vcs.sync(target, message=f"add: Task {i}", window=900).committed

    # One commit for the three mutations, and every message is preserved.
    assert _commit_count(target) == before + 1
    message = _head_message(target)
    assert message.startswith("batch: 3 changes")
    for i in range(3):
        assert f"- add: Task {i}" in message
    assert f"{vcs.BATCH_TRAILER}: 3" in message


def test_window_zero_keeps_one_commit_per_mutation(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    before = _commit_count(target)

    for i in range(3):
        store.create_todo(target, title=f"Task {i}")
        vcs.sync(target, message=f"add: Task {i}", network=False)

    assert _commit_count(target) == before + 3


def test_batching_leaves_the_working_tree_clean(tmp_path):
    # The whole point: history is compacted, writes are never deferred.
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    store.create_todo(target, title="Task")
    vcs.sync(target, message="add: Task", window=900)

    status = vcs.run_git(["status", "--porcelain"], cwd=target).stdout
    assert status.strip() == ""


def test_push_is_held_while_the_batch_is_open(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    store.create_todo(target, title="Task")
    held = vcs.sync(target, message="add: Task", window=900)
    assert held.committed is True
    assert held.held is True
    assert held.pushed is False

    # An explicit sync (window 0) is the escape hatch: it sends it now.
    flushed = vcs.sync(target, push_if_unchanged=True)
    assert flushed.pushed is True
    assert flushed.held is False


def test_a_pushed_commit_is_never_amended(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    store.create_todo(target, title="First")
    vcs.sync(target, message="add: First")  # window 0: committed and pushed
    pushed = vcs.run_git(["rev-parse", "HEAD"], cwd=target).stdout.strip()

    # The batch is young, but rewriting it would diverge from the remote.
    store.create_todo(target, title="Second")
    vcs.sync(target, message="add: Second", window=900)
    assert _commit_count(target) == 3  # scaffold + first + second
    assert vcs.run_git(["rev-parse", "HEAD~1"], cwd=target).stdout.strip() == pushed


def test_a_hand_written_commit_is_never_amended(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    (target / "notes.txt").write_text("mine", encoding="utf-8")
    vcs.run_git(["add", "-A"], cwd=target)
    vcs.run_git(["commit", "-m", "my own commit"], cwd=target)
    before = _commit_count(target)

    store.create_todo(target, title="Task")
    vcs.sync(target, message="add: Task", window=900)

    assert _commit_count(target) == before + 1
    assert (
        "my own commit"
        in vcs.run_git(["log", "-1", "--format=%B", "HEAD~1"], cwd=target).stdout
    )


def test_batching_is_disabled_inside_an_enclosing_repo(tmp_path):
    # Amending cannot be scoped with a pathspec, so a nested data repo keeps
    # one commit per mutation rather than risking the enclosing repo.
    outer = tmp_path / "outer"
    outer.mkdir()
    vcs.run_git(["init"], cwd=outer)
    target = outer / "data"
    vcs.setup_repo(str(target))
    assert not vcs._is_repo_root(target)
    before = _commit_count(target)

    for i in range(2):
        store.create_todo(target, title=f"Task {i}")
        vcs.sync(target, message=f"add: Task {i}", window=900)

    assert _commit_count(target) == before + 2


def test_parse_batch_ignores_a_message_without_the_trailer():
    assert vcs._parse_batch("plain commit\n\nno trailer here") is None
    assert vcs._parse_batch(f"add: Task\n\n{vcs.BATCH_TRAILER}: 1") == ["add: Task"]
