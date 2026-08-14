from __future__ import annotations

from helink.repositories import DatabaseManager
from helink.services.database_transfer_service import DatabaseTransferService


class DatabaseController:
    """Coordinates database transfer and application shutdown."""

    def __init__(self, service: DatabaseTransferService, database: DatabaseManager):
        self.service = service
        self.database = database

    def validate(self, path):
        self.service.validate(path)

    def export(self, destination):
        return self.service.export(destination)

    def import_(self, source):
        return self.service.import_(source)

    def close(self):
        self.database.close()
