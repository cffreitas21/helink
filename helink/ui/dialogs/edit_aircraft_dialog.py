"""Dialog for updating the identity of an existing aircraft."""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox,
)


class EditAircraftDialog(QDialog):
    """Select an aircraft and edit its registration, model, and serial number."""

    def __init__(self, aircraft, parent=None):
        """Populate the aircraft selector and prefill the editable fields."""
        super().__init__(parent)
        self.aircraft = tuple(aircraft)
        self.setWindowTitle('Edit Aircraft')
        self.setMinimumWidth(460)

        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(14)

        self.selector = QComboBox()
        for item in self.aircraft:
            self.selector.addItem(
                f'{item.registration}  \N{MIDDLE DOT}  {item.model}', item.id,
            )
        form.addRow('Aircraft', self.selector)

        self.registration = QLineEdit()
        self.model = QLineEdit()
        self.serial_number = QLineEdit()
        self.serial_number.setPlaceholderText('Unknown if left blank')
        form.addRow('Tail Number', self.registration)
        form.addRow('Aircraft Model', self.model)
        form.addRow('Serial Number', self.serial_number)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.selector.currentIndexChanged.connect(self._load_selected)
        self._load_selected()

    @property
    def selected_aircraft(self):
        """Return the aircraft selected for editing."""
        return self.aircraft[self.selector.currentIndex()]

    def _load_selected(self, *_):
        """Show the saved identity fields for the selected aircraft."""
        selected = self.selected_aircraft
        self.registration.setText(selected.registration)
        self.model.setText(selected.model)
        self.serial_number.setText(selected.serial_number)

    def accept(self):
        """Require tail number and model; the serial number may be empty."""
        if not self.registration.text().strip() or not self.model.text().strip():
            QMessageBox.warning(
                self, 'Missing information',
                'Enter the tail number and aircraft model.',
            )
            return
        super().accept()
