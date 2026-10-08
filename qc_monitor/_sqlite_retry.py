"""Bounded SQLite retries around complete, connection-owning operations."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import sqlite3
from time import sleep


SQLITE_TIMEOUT_SECONDS = 5.0
RETRY_DELAYS_SECONDS = (0.25, 0.5)
_event_sink = ContextVar("sqlite_retry_events", default=None)
log = logging.getLogger(__name__)


def sqlite_error(exception):
    """Find SQLite's numeric code through pandas/storage wrappers, without log parsing."""
    seen = set()
    while exception is not None and id(exception) not in seen:
        seen.add(id(exception))
        if isinstance(exception, sqlite3.Error) and hasattr(exception, "sqlite_errorcode"):
            return exception
        exception = exception.__cause__ or (
            None if exception.__suppress_context__ else exception.__context__)
    return None


def is_transient_sqlite_error(exception):
    error = sqlite_error(exception)
    return error is not None and (error.sqlite_errorcode & 0xff) in (
        sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


@contextmanager
def collect_sqlite_events(events):
    token = _event_sink.set(events)
    try:
        yield
    finally:
        _event_sink.reset(token)


def retry_sqlite(action, *, operation, source, events=None):
    """Each action must close connections and roll back before it raises.

    Only the failing operation is replayed, never its caller or an entire run.
    Successful uncontended operations create no diagnostic records.
    """
    record = {"operation": operation, "source": str(source), "attempts": 0,
              "state": "running", "failures": []}

    def publish(state):
        record["state"] = state
        sink = _event_sink.get()
        if events is not None:
            events.append(record)
        if sink is not None and sink is not events:
            sink.append(record)

    for attempt in range(1, len(RETRY_DELAYS_SECONDS) + 2):
        record["attempts"] = attempt
        try:
            result = action()
        except Exception as exc:
            error = sqlite_error(exc)
            transient = is_transient_sqlite_error(exc)
            if transient or record["failures"]:
                delay = RETRY_DELAYS_SECONDS[attempt - 1] if (
                    transient and attempt <= len(RETRY_DELAYS_SECONDS)) else 0.0
                record["failures"].append({"attempt": attempt,
                    "sqlite_code": error.sqlite_errorcode if error else None,
                    "sqlite_name": getattr(error, "sqlite_errorname", None),
                    "type": type(exc).__name__, "reason": str(exc),
                    "wait_seconds": delay})
                if delay:
                    log.warning("SQLite %s on %s: %s, attempt %d; retry in %.2fs",
                                operation, source, error.sqlite_errorname, attempt, delay)
                    sleep(delay)
                    continue
                publish("exhausted" if transient else "failed")
                exc.sqlite_retry = record
            raise
        else:
            if record["failures"]:
                publish("recovered")
                log.info("SQLite %s on %s recovered after %d attempts", operation, source, attempt)
            return result


def retry_store_method(method):
    """Placed inside the writer lease, outside connection/transaction lifetimes."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        return retry_sqlite(lambda: method(self, *args, **kwargs),
                            operation=method.__name__, source=self.db_path,
                            events=self.sqlite_operations)
    return wrapped


def retry_path_read(method):
    """Retry an archive check that owns all its read-only connections."""
    @wraps(method)
    def wrapped(path, *args, **kwargs):
        return retry_sqlite(lambda: method(path, *args, **kwargs),
                            operation=method.__name__, source=path)
    return wrapped
