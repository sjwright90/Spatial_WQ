"""Standard logging setup for the app. Replaces the old print()-for-status
convention (see CLAUDE.md Conventions).

Usage
-----
Call `configure_logging()` once per process entrypoint (app.py, server.py) -
not from library modules, to avoid attaching duplicate handlers. Every module
that needs to log gets its own logger via `get_logger(__name__)`.
"""

import logging

_NAMESPACE = "wq_spatial_app"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced under `wq_spatial_app`, e.g. get_logger(__name__)."""
    return logging.getLogger(f"{_NAMESPACE}.{name}")


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a single StreamHandler+formatter to the `wq_spatial_app` logger
    namespace. Idempotent - safe to call more than once (won't duplicate
    handlers). Call once per process entrypoint; deliberately does not touch
    the real root logger, since this app may run under gunicorn/waitress
    alongside other loggers.
    """
    namespace_logger = logging.getLogger(_NAMESPACE)
    namespace_logger.setLevel(level)
    if not namespace_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        namespace_logger.addHandler(handler)
    namespace_logger.propagate = False
