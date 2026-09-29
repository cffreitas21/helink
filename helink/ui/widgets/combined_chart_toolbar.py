"""Navigation controls scoped to the combined telemetry chart."""

from PySide6.QtCore import QSize, Qt
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT


class CombinedChartToolbar(NavigationToolbar2QT):
    toolitems = (
        ('Reset View', 'Show the entire flight and restore all scales', 'home', 'home'),
        ('Pan', 'Drag to move the view; turn off to select flight timestamps', 'move', 'pan'),
        ('Zoom Area', 'Drag a rectangle to zoom in; right-drag to zoom out', 'zoom_to_rect', 'zoom'),
    )

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent, coordinates=False)
        self.setObjectName('combinedChartToolbar')
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16, 16))
        self.setMovable(False)
        self.setFixedHeight(32)
        self.setStyleSheet(
            'QToolBar{background:transparent;border:none;padding:0;spacing:4px}'
            'QToolButton{color:#334155;background:#f8fafc;border:1px solid #cbd5e1;'
            'border-radius:5px;padding:4px 7px;font-size:12px}'
            'QToolButton:hover{background:#dbeafe;border-color:#93b7ef}'
            'QToolButton:checked{background:#dbeafe;color:#1e40af;border-color:#2563eb}'
            'QToolButton:disabled{color:#94a3b8;border-color:#e2e8f0}'
        )
        self.pan_action = next(action for action in self.actions() if action.text() == 'Pan')
        self.zoom_action = next(action for action in self.actions() if action.text() == 'Zoom Area')
        self.addSeparator()
        self.zoom_in_action = self.addAction('Zoom In')
        self.zoom_in_action.setToolTip('Zoom in around the selected timestamp')
        self.zoom_in_action.triggered.connect(lambda: canvas.zoom_view(0.8))
        self.zoom_out_action = self.addAction('Zoom Out')
        self.zoom_out_action.setToolTip('Zoom out around the selected timestamp')
        self.zoom_out_action.triggered.connect(lambda: canvas.zoom_view(1.25))

    def clear_mode(self):
        for action in (self.pan_action, self.zoom_action):
            if action.isChecked():
                action.trigger()

    def home(self, *args):
        self.clear_mode()
        self.canvas.reset_view()
        self.update()

    def drag_pan(self, event):
        super().drag_pan(event)
        self.canvas.limit_view()

    def release_pan(self, event):
        super().release_pan(event)
        self.canvas.limit_view()
        self.update()

    def release_zoom(self, event):
        super().release_zoom(event)
        self.canvas.limit_view()
        self.update()
