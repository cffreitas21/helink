"""Database import, export, validation, and lifecycle coordination."""

from __future__ import annotations

from PySide6.QtCore import Qt

from helink.repositories import DatabaseManager
from helink.services.database_transfer_service import DatabaseTransferService


class DatabaseController:
    """Coordinates database transfer and application shutdown."""

    def __init__(self, service: DatabaseTransferService, database: DatabaseManager, tasks=None):
        """Bind transfer operations, the active database, and task runner."""
        self.service = service
        self.database = database
        self.tasks = tasks

    def request_validate(self, path, on_result, on_error):
        """Validate a database file without blocking the interface."""
        return self.tasks.run_file(
            lambda _database, _progress: DatabaseManager.validate(path),
            on_result, on_error,
        )

    def request_export(self, destination, on_result, on_error):
        """Export a consistent database snapshot in a background task."""
        return self.tasks.write(
            lambda database, progress: DatabaseTransferService.export_session(
                database, destination, progress,
            ),
            on_result, on_error,
        )

    def request_import(self, source, on_result, on_error):
        """Replace the active database after releasing its UI connection."""
        # Called only after pending work has finished and confirmation was
        # accepted. Windows requires the UI connection to release the file.
        self.database.close()

        def import_file(_database, _progress):
            """Perform the replacement using an independent manager."""
            manager = DatabaseManager(self.database.path)
            try:
                return manager.import_from(source)
            finally:
                manager.close()

        def received(backup):
            """Reconnect the UI after a successful database import."""
            self.database.reopen()
            on_result(backup)

        def failed(error):
            """Reconnect the UI before reporting an import failure."""
            self.database.reopen()
            on_error(error)

        task = self.tasks.run_file(
            import_file, received, failed, writable=True,
        )
        task.cancelled.connect(self.database.reopen, Qt.QueuedConnection)
        return task

    def validate(self, path):
        """Validate an import candidate through the transfer service."""
        self.service.validate(path)

    def export(self, destination):
        """Export the active database to the requested path."""
        return self.service.export(destination)

    def import_(self, source):
        """Import a validated database through the transfer service."""
        return self.service.import_(source)

    def close(self):
        """Close the active database connection on shutdown."""
        self.database.close()
