"""JSON API: the endpoints that compose ``neverland.core`` for the web UI.

Reads return the todos and sidebar counts; writes cover capture plus the
clarify loop (edit a todo, complete it, delete it). Endpoints are plain ``def``
so FastAPI runs them in a threadpool: core is synchronous (file I/O and git),
which must not block the event loop.

Every write follows the same contract as capture: commit locally now and let
the poller own the network push (so ``sync_auto`` is cleared and one immediate
background flush is scheduled), which keeps the CLI and the server identical.
"""

from __future__ import annotations

from datetime import date

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from neverland.core import service, store, vcs
from neverland.core.todo import Todo, TodoState
from neverland.core.vocabulary import RepoConfig, load_repo_config

from .config import ServerConfig
from .schemas import (
    CaptureIn,
    DayPlanOut,
    NamedCount,
    TodoOut,
    TodoPatch,
    ViewsOut,
    VocabularyOut,
)
from .security import require_token

# The token guard runs before every endpoint (no-op when no token is set).
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

# Views backed by a single state; "all" and "today" are handled specially.
_STATE_VIEWS = {
    "inbox": TodoState.INBOX,
    "next": TodoState.NEXT,
    "waiting": TodoState.WAITING,
    "someday": TodoState.SOMEDAY,
}


def get_config(request: Request) -> ServerConfig:
    """Return the active :class:`ServerConfig` stored on the app."""
    return request.app.state.config


def _today_todos(cfg: ServerConfig) -> list[Todo]:
    """Active todos referenced in today's plan."""
    plan = store.load_day_plan(cfg.data_dir, date.today())
    ids = {e.todo_id for e in plan.entries}
    return [t for t in store.list_active(cfg.data_dir) if t.id in ids]


def _todos_for_view(cfg: ServerConfig, view: str) -> list[Todo]:
    """Resolve a sidebar view name to the todos it lists."""
    if view == "all":
        return store.list_active(cfg.data_dir)
    if view == "today":
        return _today_todos(cfg)
    state = _STATE_VIEWS.get(view)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown view: {view!r}")
    return store.list_by_state(cfg.data_dir, state)


@router.get("/vocabulary", response_model=VocabularyOut)
def read_vocabulary(cfg: ServerConfig = Depends(get_config)) -> VocabularyOut:
    """Return the editable areas and contexts."""
    repo = load_repo_config(cfg.data_dir)
    return VocabularyOut(areas=repo.areas, contexts=repo.contexts)


@router.get("/views", response_model=ViewsOut)
def read_views(cfg: ServerConfig = Depends(get_config)) -> ViewsOut:
    """Return the sidebar counts: fixed buckets plus per-area/context."""
    repo = load_repo_config(cfg.data_dir)
    active = store.list_active(cfg.data_dir)

    def _count(state: TodoState) -> int:
        return sum(1 for t in active if t.state is state)

    areas = [
        NamedCount(name=a, count=sum(1 for t in active if t.area == a))
        for a in repo.areas
    ]
    contexts = [
        NamedCount(name=c, count=sum(1 for t in active if t.context == c))
        for c in repo.contexts
    ]
    return ViewsOut(
        inbox=_count(TodoState.INBOX),
        today=len(_today_todos(cfg)),
        all=len(active),
        next=_count(TodoState.NEXT),
        waiting=_count(TodoState.WAITING),
        someday=_count(TodoState.SOMEDAY),
        areas=areas,
        contexts=contexts,
    )


@router.get("/todos", response_model=list[TodoOut])
def read_todos(
    view: str = "all",
    area: str | None = None,
    context: str | None = None,
    cfg: ServerConfig = Depends(get_config),
) -> list[TodoOut]:
    """Return the todos of a view, optionally filtered by area and context."""
    todos = _todos_for_view(cfg, view)
    if area is not None:
        todos = [t for t in todos if t.area == area]
    if context is not None:
        todos = [t for t in todos if t.context == context]
    return [TodoOut.from_todo(t) for t in todos]


@router.get("/today", response_model=DayPlanOut)
def read_today(cfg: ServerConfig = Depends(get_config)) -> DayPlanOut:
    """Return today's plan (entries with their per-day status)."""
    plan = store.load_day_plan(cfg.data_dir, date.today())
    return DayPlanOut.from_plan(plan)


@router.post("/capture", response_model=TodoOut, status_code=201)
def capture(
    payload: CaptureIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Capture a todo into the inbox (GTD capture, zero decisions).

    The write is committed locally right away; the network push is left to the
    poller, plus one immediate background flush so a capture propagates without
    waiting a full poll interval. Both take the shared lock, so they never
    collide.
    """
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")

    repo = load_repo_config(cfg.data_dir)
    repo.sync_auto = False  # the poller owns the network sync, not a subprocess
    todo, _ = service.capture(cfg.data_dir, repo, title)

    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


# --------------------------------------------------------------------------- #
# Writes: clarify, complete, delete                                            #
# --------------------------------------------------------------------------- #


def _repo_for_write(cfg: ServerConfig) -> RepoConfig:
    """Load the repo config with the background network flush disabled.

    Like capture, every mutation commits locally now and leaves the push to the
    poller, so ``sync_auto`` is cleared to avoid spawning a rival flush process.
    """
    repo = load_repo_config(cfg.data_dir)
    repo.sync_auto = False
    return repo


def _require_active(cfg: ServerConfig, todo_id: str) -> Todo:
    """Return the active todo with ``todo_id`` or raise ``404``."""
    todo = store.find_active(cfg.data_dir, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail=f"unknown todo: {todo_id}")
    return todo


def _apply_patch(cfg: ServerConfig, repo: RepoConfig, todo: Todo, fields: dict) -> None:
    """Validate the patched ``fields`` against the vocabulary and apply them.

    Only keys present in ``fields`` are touched; an explicit ``None`` clears the
    field. ``area``, ``context`` and ``project`` must reference known values, so
    a typo cannot orphan a todo onto a value nothing else uses.
    """
    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        todo.title = title
    if "state" in fields:
        try:
            todo.state = TodoState(fields["state"])
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"unknown state: {fields['state']!r}"
            ) from None
    if "area" in fields:
        area = fields["area"]
        if area is not None and area not in repo.areas:
            raise HTTPException(status_code=400, detail=f"unknown area: {area!r}")
        todo.area = area
    if "context" in fields:
        context = fields["context"]
        if context is not None and context not in repo.contexts:
            raise HTTPException(status_code=400, detail=f"unknown context: {context!r}")
        todo.context = context
    if "project" in fields:
        project = fields["project"]
        if project is not None:
            known = {p.id for p in store.list_active_projects(cfg.data_dir)}
            if project not in known:
                raise HTTPException(
                    status_code=400, detail=f"unknown project: {project!r}"
                )
        todo.project = project
    if "waiting_on" in fields:
        todo.waiting_on = fields["waiting_on"] or None


@router.patch("/todos/{todo_id}", response_model=TodoOut)
def update_todo(
    todo_id: str,
    payload: TodoPatch,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Apply a partial edit to a todo (clarify, defer, delegate, rename).

    Only the fields present in the body are changed. Setting ``state`` to
    ``done`` is a completion, so it is routed through the archive path rather
    than an in-place rewrite.
    """
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("state") == TodoState.DONE.value:
        service.complete(cfg.data_dir, repo, [todo])
    else:
        _apply_patch(cfg, repo, todo, fields)
        service.update(cfg.data_dir, repo, todo)

    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


@router.post("/todos/{todo_id}/complete", response_model=TodoOut)
def complete_todo(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Complete a todo: archive it and tick it in today's plan."""
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.complete(cfg.data_dir, repo, [todo])
    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


@router.delete("/todos/{todo_id}", status_code=204)
def delete_todo(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> Response:
    """Permanently delete a todo."""
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.delete(cfg.data_dir, repo, [todo])
    background.add_task(vcs.background_flush, cfg.data_dir)
    return Response(status_code=204)
