"""Transfer database files without exposing partial exports."""

import os
from pathlib import Path
import sqlite3
import tempfile

from helink.repositories.database_manager import DatabaseManager


class DatabaseTransferService:
    """Coordinate validation, import, and export of HELINK databases."""

    def __init__(self,database):
        """Store the manager used for validation and file transfers."""
        self.database=database

    def validate(self,path):
        """Check that a database file can be imported safely."""
        self.database.validate(path)

    def export(self,destination):
        """Write a backup of the current database."""
        return self.database.export_to(destination)

    def import_(self,source):
        """Replace the current database with a validated backup."""
        return self.database.import_from(source)

    @staticmethod
    def export_session(database, destination, progress):
        """Export atomically through a temporary file with progress updates."""
        destination = Path(destination).resolve()
        if destination == database.path.resolve():
            raise ValueError('Select a different destination file.')
        temporary = tempfile.NamedTemporaryFile(
            prefix='.helink-export-', suffix='.db', dir=destination.parent, delete=False,
        )
        temporary_path = Path(temporary.name)
        temporary.close()
        try:
            target = sqlite3.connect(temporary_path)
            try:
                database.connection.backup(
                    target, pages=512,
                    progress=lambda _status, remaining, total: progress(
                        95 * (total - remaining) / max(1, total), 'Exporting database...',
                    ),
                )
                target.commit()
            finally:
                target.close()
            DatabaseManager.validate(temporary_path)
            progress(99, 'Finalizing database export...')
            os.replace(temporary_path, destination)
            progress(100, 'Database export complete.')
            return destination
        finally:
            temporary_path.unlink(missing_ok=True)
