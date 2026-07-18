"""Server configuration, read from the environment.

Everything the server needs to run is a plain value read from ``PYTODO_SERVER_*``
environment variables (with a config-file fallback added later). Keeping config
in the environment is what makes a systemd unit and a container consume it
identically, so one can replace the other without touching the app.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pytodo.core.settings import read_data_dir

ENV_DATA_DIR = "PYTODO_SERVER_DATA_DIR"
ENV_HOST = "PYTODO_SERVER_HOST"
ENV_PORT = "PYTODO_SERVER_PORT"
ENV_TOKEN = "PYTODO_SERVER_TOKEN"
ENV_POLL_INTERVAL = "PYTODO_SERVER_POLL_INTERVAL"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_POLL_INTERVAL = 30.0


class ConfigError(RuntimeError):
    """The server cannot start with the given environment."""


@dataclass
class ServerConfig:
    """Resolved server configuration.

    Attributes
    ----------
    data_dir : pathlib.Path
        Data repo the server reads and writes (a git working copy).
    host : str
        Bind address. Defaults to loopback; set it to the wireguard interface to
        expose the server only inside the tunnel, never ``0.0.0.0`` publicly.
    port : int
        Bind port.
    token : str or None
        Shared secret required on every request (enforced from step 4). ``None``
        leaves the server unauthenticated (dev only).
    poll_interval : float
        Seconds between background ``git pull`` cycles (used from step 2).
    """

    data_dir: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ServerConfig:
        """Build a config from ``PYTODO_SERVER_*`` variables.

        The data repo comes from ``PYTODO_SERVER_DATA_DIR`` or, failing that, the
        machine-local repo the CLI uses (:func:`pytodo.core.settings.read_data_dir`).

        Raises
        ------
        ConfigError
            No data repo could be resolved, or a numeric value is malformed.
        """
        env = os.environ if environ is None else environ

        raw_dir = env.get(ENV_DATA_DIR)
        data_dir = Path(raw_dir).expanduser() if raw_dir else read_data_dir()
        if data_dir is None:
            raise ConfigError(
                f"No data repo: set {ENV_DATA_DIR} or run `todo init` first."
            )
        if not data_dir.exists():
            raise ConfigError(f"Data repo not found: {data_dir}")

        return cls(
            data_dir=data_dir,
            host=env.get(ENV_HOST, DEFAULT_HOST),
            port=_int(env, ENV_PORT, DEFAULT_PORT),
            token=env.get(ENV_TOKEN) or None,
            poll_interval=_float(env, ENV_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {value!r}") from exc


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    value = env.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {value!r}") from exc
