"""Reentrant per-archive writer leases (Linux/macOS); never used by inspections."""
from contextlib import contextmanager
import fcntl
from functools import wraps
from pathlib import Path
import threading


class WriterBusyError(RuntimeError):
    pass


_guard = threading.Lock()
_leases = {}


@contextmanager
def writer_lease(database):
    path = Path(database).expanduser().resolve()
    owner = threading.get_ident()
    with _guard:
        entry = _leases.get(path)
        if entry:
            if entry[0] != owner:
                raise WriterBusyError(f'Archive already in use: {path}')
            entry[2] += 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.with_name(path.name + '.lock').open('a+b')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise WriterBusyError(f'Archive already in use: {path}') from exc
            except BaseException:
                handle.close()
                raise
            entry = [owner, handle, 1]
            _leases[path] = entry
    try:
        yield
    finally:
        with _guard:
            entry[2] -= 1
            if entry[2] == 0:
                del _leases[path]
                entry[1].close()  # OS also releases flock after process termination.
    # Keep the lock inode: unlinking it would let writers lock different files.


def locked_store_method(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.write_session():
            return method(self, *args, **kwargs)
    return wrapped


def locked_coordinator(method):
    """The store is the second argument of family coordinators."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        qc_database = kwargs.get('qc_database', args[1] if len(args) > 1 else None)
        # Inspection must not acquire or create a lease even with a writable store.
        dry_run = kwargs.get('dry_run', args[2] if len(args) > 2 else False)
        if dry_run:
            return method(*args, **kwargs)
        with qc_database.write_session():
            return method(*args, **kwargs)
    return wrapped
