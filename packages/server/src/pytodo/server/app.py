"""FastAPI application factory.

:func:`create_app` turns a :class:`ServerConfig` into a ready app. It is the
reuse surface: another project can build its own config, call this, and mount
the result, or add its own routes on top.
"""

from __future__ import annotations

from fastapi import FastAPI

from . import api
from .config import ServerConfig


def create_app(config: ServerConfig) -> FastAPI:
    """Build the pytodo FastAPI app for ``config``.

    Parameters
    ----------
    config : ServerConfig
        Resolved server configuration; stored on ``app.state.config`` for the
        route dependencies to read.

    Returns
    -------
    fastapi.FastAPI
        The application, with the read API mounted under ``/api``.
    """
    app = FastAPI(title="pytodo", version="0.3.0")
    app.state.config = config
    app.include_router(api.router)
    return app
