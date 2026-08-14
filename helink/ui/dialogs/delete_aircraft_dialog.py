from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QInputDialog,
    QLabel, QMessageBox,
)


class DeleteAircraftDialog(QDialog):
    def __init__(self, aircraft, parent=None):
        super().__init__(parent)
        self.aircraft = list(aircraft)
        self.setWindowTitle('Delete Aircraft')
        self.setMinimumWidth(460)

        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(14)

        self.selector = QComboBox()
        for item in self.aircraft:
            self.selector.addItem(
                f'{item.registration}  \u00b7  {item.model}', item.id
            )
        form.addRow('Aircraft', self.selector)

        warning = QLabel(
            'The selected aircraft and all associated flights and data '
            'will be permanently deleted.'
        )
        warning.setWordWrap(True)
        warning.setObjectName('muted')
        form.addRow(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText('Continue')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def selected_aircraft(self):
        aircraft_id = self.selector.currentData()
        return next(
            item for item in self.aircraft if item.id == aircraft_id
        )

    def accept(self):
        aircraft = self.selected_aircraft
        registration = aircraft.registration
        answer = QMessageBox.warning(
            self,
            'Delete aircraft',
            f'Do you want to delete aircraft {registration}?\n\n'
            'All associated flights and data will also be permanently deleted.',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            self.reject()
            return

        confirmation, accepted = QInputDialog.getText(
            self,
            'Final confirmation',
            f'This action cannot be undone.\n'
            f'To delete {registration}, type exactly: Delete',
        )
        if not accepted:
            self.reject()
            return
        if confirmation != 'Delete':
            QMessageBox.information(
                self,
                'Deletion cancelled',
                'The text entered does not match "Delete". '
                'The aircraft was not deleted.',
            )
            self.reject()
            return
        super().accept()
