from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox,
)


class AddAircraftDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Register New Aircraft')
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.prefix = QLineEdit()
        self.model = QLineEdit('Leonardo AW119 Koala')
        self.serial_number = QLineEdit()
        form.addRow('Tail Number', self.prefix)
        form.addRow('Aircraft Model', self.model)
        form.addRow('Serial Number', self.serial_number)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        if not self.prefix.text().strip():
            QMessageBox.warning(
                self, 'Missing information', 'Enter the aircraft registration.'
            )
            return
        super().accept()
