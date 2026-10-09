"""Background work, bounded read caching, and cooperative cancellation."""

from collections import OrderedDict
from pathlib import Path
import sqlite3
from threading import Event, Lock
from time import monotonic
from types import SimpleNamespace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal


class TaskHandle(QObject):
    """Expose cancellation, progress, and completion signals for one task."""
    succeeded = Signal(object)
    failed = Signal(object)
    progress = Signal(float, str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, parent=None):
        """Create cancellation state and progress signals for one task."""
        super().__init__(parent)
        self.stop = Event()
        self._last_progress = 0.0

    def cancel(self):
        """Request cooperative cancellation of the running operation."""
        self.stop.set()

    def check_cancelled(self):
        """Raise when the caller has requested cancellation."""
        if self.stop.is_set():
            raise InterruptedError('Operation cancelled.')

    def report(self, value, message):
        """Emit throttled progress updates while respecting cancellation."""
        # The completion notification is sent after a committed import.
        if value < 100:
            self.check_cancelled()
        now = monotonic()
        if value >= 100 or now - self._last_progress >= 0.04:
            self._last_progress = now
            self.progress.emit(float(value), str(message))


class _DatabaseTask(QRunnable):
    """Execute one read or serialized write on a worker-owned connection."""
    """Execute one read or serialized write on a worker-owned connection."""
    def __init__(self, path, handle, operation, writable, write_lock):
        """Capture the database path and operation for a worker thread."""
        super().__init__()
        self.path = path
        self.handle = handle
        self.operation = operation
        self.writable = writable
        self.write_lock = write_lock

    def run(self):
        """Run the operation and emit success, cancellation, or failure."""
        """Run the operation and emit success, cancellation, or failure."""
        connection = None
        acquired = False
        try:
            self.handle.check_cancelled()
            if self.writable:
                while not self.write_lock.acquire(timeout=0.05):
                    self.handle.check_cancelled()
                acquired = True
                self.handle.check_cancelled()
            database = None
            if self.path is not None:
                uri = self.path.as_uri() + ('?mode=rw' if self.writable else '?mode=ro')
                connection = sqlite3.connect(uri, uri=True, timeout=5)
                connection.row_factory = sqlite3.Row
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA temp_store=MEMORY')
                connection.execute('PRAGMA cache_size=-8192')
                if self.writable:
                    connection.execute('PRAGMA synchronous=NORMAL')
                connection.set_progress_handler(
                    lambda: int(self.handle.stop.is_set()), 2000,
                )
                database = SimpleNamespace(connection=connection, path=self.path)
            result = self.operation(database, self.handle.report)
            if not self.writable:
                self.handle.check_cancelled()
            self.handle.succeeded.emit(result)
        except Exception as error:
            if isinstance(error, InterruptedError) or (
                self.handle.stop.is_set()
                and isinstance(error, sqlite3.OperationalError)
                and 'interrupt' in str(error).lower()
            ):
                self.handle.cancelled.emit()
            else:
                self.handle.failed.emit(error)
        finally:
            if connection is not None:
                connection.close()
            if acquired:
                self.write_lock.release()
            self.handle.finished.emit()


def _freeze(value):
    """Convert nested cache-key arguments into hashable tuples."""
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


class TaskController(QObject):
    """Runs no widget code; all completion handlers return to the UI thread."""

    idle = Signal()
    MAX_CACHE_ENTRIES = 32
    MAX_FLIGHT_SNAPSHOTS = 2

    def __init__(self, database, parent=None):
        """Create the worker pool and bounded query cache for a database."""
        super().__init__(parent)
        self.database = database
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._write_lock = Lock()
        self._active = set()
        self._cache = OrderedDict()
        self._revision = None

    @property
    def busy(self):
        """Whether any background task is still active."""
        return bool(self._active)

    def _database_revision(self):
        """Read signals that change when local or external database writes occur."""
        connection = self.database.connection
        return (
            id(connection), connection.total_changes,
            connection.execute('PRAGMA data_version').fetchone()[0],
        )

    def invalidate(self):
        """Discard cached query results after database changes."""
        self._cache.clear()
        self._revision = None

    def query(self, operation, on_result, on_error, *, cache_key=None):
        """Run a read task, reusing a revision-matched cached result if present."""
        revision = self._database_revision()
        if revision != self._revision:
            self._cache.clear()
            self._revision = revision
        key = _freeze(cache_key) if cache_key is not None else None

        def received(value):
            """Cache a successful read only if the database revision still matches."""
            if key is not None and revision == self._database_revision():
                self._cache[key] = value
                self._cache.move_to_end(key)
                heavy = [
                    item for item, payload in self._cache.items()
                    if hasattr(payload, 'engine_data') or hasattr(payload, 'flight')
                ]
                for item in heavy[:-self.MAX_FLIGHT_SNAPSHOTS]:
                    self._cache.pop(item, None)
                while len(self._cache) > self.MAX_CACHE_ENTRIES:
                    self._cache.popitem(last=False)
            on_result(value)

        if key is not None and key in self._cache:
            value = self._cache[key]
            self._cache.move_to_end(key)
            handle = self._connect(on_result, on_error)

            def deliver():
                """Deliver a cached result on the next UI event-loop cycle."""
                if not handle.stop.is_set():
                    handle.succeeded.emit(value)
                else:
                    handle.cancelled.emit()
                handle.finished.emit()

            QTimer.singleShot(0, deliver)
            return handle
        return self._start(operation, received, on_error, writable=False)

    def write(self, operation, on_result, on_error, *, on_progress=None):
        """Run a serialized write task and invalidate cached reads on success."""
        def received(value):
            """Invalidate cached reads after a successful write."""
            self.invalidate()
            on_result(value)
        return self._start(
            operation, received, on_error, writable=True, on_progress=on_progress,
        )

    def _connect(self, on_result, on_error, on_progress=None):
        """Create a task handle and connect callbacks on the UI thread."""
        handle = TaskHandle(self)
        self._active.add(handle)
        handle.succeeded.connect(on_result, Qt.QueuedConnection)
        handle.failed.connect(on_error, Qt.QueuedConnection)
        if on_progress is not None:
            handle.progress.connect(on_progress, Qt.QueuedConnection)
        handle.finished.connect(lambda: self._finished(handle), Qt.QueuedConnection)
        return handle

    def run_file(self, operation, on_result, on_error, *, writable=False):
        """Transfer jobs own their connections, including during file replacement."""
        def received(value):
            """Invalidate cached reads after a file-level write."""
            if writable:
                self.invalidate()
            on_result(value)
        handle = self._connect(received, on_error)
        self.pool.start(_DatabaseTask(
            None, handle, operation, writable, self._write_lock,
        ))
        return handle

    def _start(self, operation, on_result, on_error, *, writable, on_progress=None):
        """Submit a database task to the worker pool."""
        handle = self._connect(on_result, on_error, on_progress)
        self.pool.start(_DatabaseTask(
            Path(self.database.path).resolve(), handle, operation,
            writable, self._write_lock,
        ))
        return handle

    def _finished(self, handle):
        """Remove a completed handle and announce when all tasks are idle."""
        self._active.discard(handle)
        handle.deleteLater()
        if not self._active:
            self.idle.emit()

    def cancel_all(self):
        """Request cancellation of every active background task."""
        for handle in tuple(self._active):
            handle.cancel()
