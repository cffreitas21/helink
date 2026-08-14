from PySide6.QtWidgets import QLabel

from helink.ui.widgets.card import Card


class Metric(Card):
    def __init__(self, label, value, sub=''):
        super().__init__()
        value_label = QLabel(str(value))
        value_label.setStyleSheet(
            'font-size:25px;font-weight:800;color:#0f172a'
        )
        self.layout.addWidget(value_label)
        label_widget = QLabel(label)
        label_widget.setObjectName('muted')
        self.layout.addWidget(label_widget)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setObjectName('muted')
            self.layout.addWidget(sub_label)
