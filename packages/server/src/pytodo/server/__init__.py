"""pytodo server: a self-hosted FastAPI app and web UI over ``pytodo.core``.

The server is a frontend on the shared core, exactly like the CLI: it composes
:mod:`pytodo.core` and never reimplements the todo logic. :func:`create_app`
builds a FastAPI application from a :class:`~pytodo.server.config.ServerConfig`,
so others can mount it in their own server or point it at their own data repo.
"""
