"""Shared error-handling decorators for @app.callback functions.

Generalizes the two ad hoc try/except patterns that used to be hand-rolled per
callback (log+no_update, log+surface-error-to-UI) into reusable decorators, so
every callback gets consistent logging instead of an inconsistent mix of
print(), bare try/except, or no handling at all.

Stacking order with the existing `callback_prevent_initial_output` decorator
(src/callbacks.py):

    @app.callback(...)
    @log_and_surface_error(...)  # or @log_and_prevent_update(...)
    @callback_prevent_initial_output
    def my_callback(...):
        ...
"""

from functools import wraps
from typing import Any, Callable

import dash

from .logging_config import get_logger


def log_and_prevent_update(logger_name: str, fallback: Any = dash.no_update) -> Callable:
    """Decorator for callbacks with no interactive error-surfacing need: catches
    Exception, logs it via get_logger(logger_name).exception(...), and returns
    `fallback` instead of propagating.

    For multi-output callbacks, pass fallback=tuple([dash.no_update] * n_outputs)
    explicitly - output arity varies per callback, so it isn't auto-inferred.
    """

    def decorator(func: Callable) -> Callable:
        logger = get_logger(logger_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except dash.exceptions.PreventUpdate:
                raise
            except Exception:
                logger.exception("Unhandled error in callback %s", func.__name__)
                return fallback

        return wrapper

    return decorator


def log_and_surface_error(
    logger_name: str,
    error_output_index: int = 0,
    fallback: Any = dash.no_update,
) -> Callable:
    """Decorator for callbacks that report errors into a UI text/Alert component
    (matches save_session_data_to_redis's existing pattern). Catches Exception,
    logs it via .exception(...), and returns a tuple matching the callback's
    Output arity where position `error_output_index` is f"Error: {e}" and every
    other position is `fallback`.

    `fallback` must already reflect the callback's non-error output arity minus
    the error slot - pass fallback=tuple([dash.no_update] * (n_outputs - 1)) for
    multi-output callbacks (the error message is inserted at error_output_index).
    """

    def decorator(func: Callable) -> Callable:
        logger = get_logger(logger_name)

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except dash.exceptions.PreventUpdate:
                raise
            except Exception as e:
                logger.exception("Unhandled error in callback %s", func.__name__)
                if isinstance(fallback, tuple):
                    result = list(fallback)
                    result.insert(error_output_index, f"Error: {e}")
                    return tuple(result)
                return f"Error: {e}"

        return wrapper

    return decorator
