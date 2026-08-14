STYLE='''
QWidget{font-family:Segoe UI,Arial;font-size:13px;color:#111827;background:#f1f5f9}
QMainWindow{background:#f4f7fb} QFrame#sidebar{background:#0b1220;border:none}
QLabel{background:transparent} QLabel#brand{font-size:19px;font-weight:700;color:#ffffff} QLabel#muted{color:#475569} QLabel#title{font-size:24px;font-weight:750;color:#0f172a}
QPushButton{background:#0b1220;color:#ffffff;border:1px solid #0b1220;border-radius:8px;padding:9px 14px;font-weight:650} QPushButton:hover{background:#1e293b;border-color:#1e293b} QPushButton:pressed{background:#020617;border-color:#020617} QPushButton:focus{border:2px solid #64748b} QPushButton:disabled{background:#d1d5db;color:#4b5563;border-color:#d1d5db}
QPushButton#nav{background:transparent;color:#dbe4f0;border:none;text-align:left;padding:11px 12px;border-radius:8px} QPushButton#nav:hover,QPushButton#nav:checked{background:#263449;color:#ffffff}
QPushButton#secondary{background:#ffffff;color:#1e293b;border:1px solid #94a3b8} QPushButton#secondary:hover{background:#eaf0f6;border-color:#64748b} QPushButton#danger{background:#b91c1c;border-color:#b91c1c;color:#ffffff} QPushButton#danger:hover{background:#991b1b;border-color:#991b1b}
QPushButton#deleteAircraft{background:#ffffff;color:#991b1b;border:1px solid #dc2626;padding:8px 11px} QPushButton#deleteAircraft:hover{background:#fee2e2;border-color:#b91c1c}
QToolButton#fileList{background:#e2e8f0;color:#1e293b;border:1px solid #94a3b8;border-radius:7px;padding:7px 11px;font-weight:650} QToolButton#fileList:hover{background:#dbeafe;color:#1e3a8a;border-color:#60a5fa} QToolButton#fileList::menu-indicator{image:none}
QMenuBar{background:#ffffff;color:#0f172a;border-bottom:1px solid #cbd5e1;padding:3px 8px} QMenuBar::item{background:transparent;padding:6px 12px;border-radius:5px} QMenuBar::item:selected{background:#dbeafe;color:#0f172a}
QMenu{background:#ffffff;color:#111827;border:1px solid #94a3b8;padding:6px} QMenu::item{padding:7px 24px 7px 10px;border-radius:4px} QMenu::item:selected{background:#dbeafe;color:#0f172a} QMenu::item:disabled{color:#475569;font-weight:600}
QFrame#card,QFrame#aircraftRow{background:#ffffff;border:1px solid #cbd5e1;border-radius:11px} QFrame#aircraftRow:hover{border:1px solid #3b82f6;background:#f8fbff}
QFrame#aircraftIcon{background:#dbeafe;border:1px solid #93c5fd;border-radius:10px}
QFrame#statBox{background:#f1f5f9;border:1px solid #cbd5e1;border-radius:9px}
QLabel#statValue{color:#0f172a;font-size:16px;font-weight:750} QLabel#statLabel{color:#334155;font-size:11px;font-weight:650}
QLabel#badge{background:#f1f5f9;color:#475569;border-radius:10px;padding:4px 9px;font-size:12px;font-weight:600} QLabel#alertBadge{background:#fff7ed;color:#c2410c;border-radius:10px;padding:4px 9px;font-size:12px;font-weight:600}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{background:#ffffff;color:#111827;border:1px solid #94a3b8;border-radius:7px;padding:8px;selection-background-color:#2563eb;selection-color:#ffffff} QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus{border:2px solid #2563eb}
QTableWidget{background:#ffffff;alternate-background-color:#eef2f7;color:#111827;border:1px solid #94a3b8;border-radius:9px;gridline-color:#cbd5e1;selection-background-color:#bfdbfe;selection-color:#0f172a} QHeaderView::section{background:#e2e8f0;padding:9px;border:none;border-right:1px solid #cbd5e1;border-bottom:1px solid #94a3b8;font-weight:700;color:#1e293b}
QTabWidget::pane{border:1px solid #94a3b8;background:#ffffff} QTabBar::tab{background:#cbd5e1;color:#334155;border:1px solid #94a3b8;padding:9px 16px;font-weight:600} QTabBar::tab:hover{background:#dbeafe;color:#1e3a8a} QTabBar::tab:selected{background:#ffffff;color:#1d4ed8;border-bottom-color:#ffffff;font-weight:750}
QTextEdit,QListWidget{background:#ffffff;color:#111827;border:1px solid #94a3b8;border-radius:8px;padding:8px;selection-background-color:#bfdbfe;selection-color:#0f172a}
QScrollArea{background:transparent;border:none} QScrollBar:vertical{background:#e2e8f0;width:11px;margin:2px} QScrollBar::handle:vertical{background:#64748b;border-radius:5px;min-height:32px} QScrollBar::handle:vertical:hover{background:#475569} QToolTip{background:#0f172a;color:#ffffff;border:1px solid #334155;padding:6px}

QLabel#listSummary{color:#475569;font-size:12px;font-weight:600}
QTableWidget#flightTable{background:#ffffff;alternate-background-color:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;selection-background-color:transparent;gridline-color:transparent}
QTableWidget#flightTable::item{padding:8px 10px;border-bottom:1px solid #e2e8f0;color:#172033}
QTableWidget#flightTable QHeaderView::section{background:#e8eef6;color:#25344a;border:none;border-right:1px solid #d3dce8;border-bottom:1px solid #aebed2;padding:11px 10px;font-size:11px;font-weight:750}
QWidget#tableActions{background:transparent}
QPushButton#tableAction{background:#0b1220;color:#ffffff;border:1px solid #0b1220;border-radius:7px;padding:7px 12px}
QPushButton#tableAction:hover{background:#1e293b;border-color:#1e293b}
QPushButton#tableDelete{background:#ffffff;color:#b91c1c;border:1px solid #dc2626;border-radius:7px;padding:7px 12px}
QPushButton#tableDelete:hover{background:#fee2e2;color:#991b1b;border-color:#b91c1c}

QLabel#overviewCaption{color:#64748b;font-size:10px;font-weight:750;letter-spacing:.5px}
QLabel#overviewValue{color:#0f172a;font-size:16px;font-weight:750}
QFrame#overviewMetric{background:#f8fafc;border:1px solid #d7e0eb;border-radius:8px}
QLabel#overviewMetricValue{color:#0f172a;font-size:18px;font-weight:800}
QLabel#overviewMetricLabel{color:#526175;font-size:10px;font-weight:700}
QLabel#overviewBody{color:#334155;font-size:13px;line-height:1.45}
QFrame#filesPanel{background:#f8fafc;border:1px solid #bdcad9;border-radius:11px}
QListWidget#overviewFiles{background:#ffffff;border:1px solid #d3dce8;border-radius:7px;padding:4px}
QListWidget#overviewFiles::item{padding:8px 7px;border-bottom:1px solid #edf1f5;color:#26364c}

QFrame#overviewParameter{background:#f8fafc;border:1px solid #d7e0eb;border-radius:8px}
QLabel#overviewParameterTitle{color:#334155;font-size:11px;font-weight:750}
QToolButton#eventTotal{background:#eef2f7;border:1px solid #cbd5e1;border-radius:8px}
QToolButton#eventCas{background:#e8f1ff;border:1px solid #93b7ef;border-radius:8px}
QToolButton#eventExceedance{background:#fff1e8;border:1px solid #f0ad75;border-radius:8px}
QToolButton#eventWarning{background:#feecec;border:1px solid #ef9a9a;border-radius:8px}
QToolButton#eventCaution{background:#fff8dd;border:1px solid #e8c85f;border-radius:8px}
QLabel#eventValue{color:#172033;font-size:18px;font-weight:850}
QLabel#eventLabel{color:#45556d;font-size:9px;font-weight:750}

QToolButton#triggerList{background:#e8eef6;color:#1e3a5f;border:1px solid #9fb2c9;border-radius:7px;padding:6px 10px;font-weight:700}
QToolButton#triggerList:hover{background:#dbeafe;color:#1d4ed8;border-color:#7aa7e8}
QToolButton#triggerList::menu-indicator{image:none}
QTableWidget#alertsTable::item{padding:7px 9px;border-bottom:1px solid #e2e8f0}

QToolButton#eventMiscmp{background:#f3e8ff;border:2px solid #a855f7;border-radius:8px} QToolButton#eventMiscmp QLabel#eventValue{color:#7e22ce} QToolButton#eventMiscmp QLabel#eventLabel{color:#6b21a8}

QToolButton#eventTotal:hover,QToolButton#eventExceedance:hover,QToolButton#eventWarning:hover,QToolButton#eventCaution:hover,QToolButton#eventMiscmp:hover{border-color:#2563eb}
QToolButton#eventTotal::menu-indicator,QToolButton#eventExceedance::menu-indicator,QToolButton#eventWarning::menu-indicator,QToolButton#eventCaution::menu-indicator,QToolButton#eventMiscmp::menu-indicator{image:none}

QToolButton#eventTotal,QToolButton#eventExceedance,QToolButton#eventWarning,QToolButton#eventCaution,QToolButton#eventMiscmp{padding:0px;margin:0px}

QWidget#stateCell{background:transparent}
QLabel#stateSet{background:#fee2e2;color:#991b1b;border:1px solid #f29a9a;border-radius:12px;font-size:10px;font-weight:800}
QLabel#stateCleared{background:#dcfce7;color:#166534;border:1px solid #86d6a0;border-radius:12px;font-size:10px;font-weight:800}
QLabel#stateNeutral{background:#e2e8f0;color:#475569;border:1px solid #b8c4d1;border-radius:12px;font-size:10px;font-weight:800}
'''
