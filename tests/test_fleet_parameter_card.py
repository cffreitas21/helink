"""Compact fleet card checks with synthetic data and no database access."""

import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QWidget

from helink.models.aircraft import Aircraft
from helink.ui.pages.dashboard_page import DashboardPage
from helink.ui.theme import STYLE
from helink.ui.widgets import FleetParameterCard


class FleetParameterCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path('C:/Windows/Fonts/segoeui.ttf')
        if os.name == 'nt' and font.exists():
            QFontDatabase.addApplicationFont(str(font))
        cls.app.setStyleSheet(STYLE)

    def make_card(self, title='ENG OIL TEMP', average=85, maximum=105, unit='\u00b0C'):
        card = FleetParameterCard(title, average, maximum, unit)
        card.show()
        self.app.processEvents()
        self.addCleanup(card.deleteLater)
        self.addCleanup(card.close)
        return card

    def test_compact_card_keeps_height_and_original_font_sizes(self):
        card = self.make_card()
        self.assertEqual(card.height(), 68)
        self.assertEqual(card.width(), 120)
        for label in card.findChildren(QLabel, 'fleetParameterValue'):
            self.assertEqual(label.font().pixelSize(), 15)
        self.assertEqual(
            card.findChild(QLabel, 'fleetParameterTitle').font().pixelSize(), 10,
        )
        for label in card.findChildren(QLabel, 'fleetParameterStatistic'):
            self.assertEqual(label.font().pixelSize(), 10)

    def test_all_parameter_labels_remain_readable_inside_the_card(self):
        for title, unit in (
            ('ITT', '\u00b0C'), ('ENG OIL TEMP', '\u00b0C'),
            ('ENG OIL PRESS', 'psi'), ('XMSN OIL TEMP', '\u00b0C'),
            ('XMSN OIL PRESS', 'psi'), ('FUEL PRESS', 'psi'),
        ):
            with self.subTest(parameter=title):
                card = self.make_card(title, 125.5, 150.2, unit)
                for label in card.findChildren(QLabel):
                    self.assertGreaterEqual(label.x(), 0)
                    self.assertGreaterEqual(label.y(), 0)
                    self.assertLess(label.geometry().right(), card.width())
                    self.assertLess(label.geometry().bottom(), card.height())
                    self.assertGreaterEqual(
                        label.width(), label.fontMetrics().horizontalAdvance(label.text()),
                    )
                    self.assertGreaterEqual(label.height(), label.fontMetrics().height())

    def test_avg_and_max_columns_stay_aligned_and_missing_values_use_dashes(self):
        card = self.make_card(average=None, maximum=None)
        captions = card.findChildren(QLabel, 'fleetParameterStatistic')
        values = card.findChildren(QLabel, 'fleetParameterValue')
        self.assertEqual([caption.text() for caption in captions], ['AVG', 'MAX'])
        self.assertEqual([value.text() for value in values], ['\u2014', '\u2014'])
        self.assertEqual(values[0].y(), values[1].y())
        for caption, value in zip(captions, values):
            self.assertEqual(caption.geometry().center().x(), value.geometry().center().x())
            self.assertLess(caption.geometry().bottom(), value.y())

    def test_dashboard_keeps_all_six_cards_on_one_row_and_view_flights_working(self):
        controller = Mock()
        controller.list_aircraft.return_value = [
            Aircraft(id='test', registration='TEST', model='Test Model',
                     serial_number='SN-TEST', flight_count=4),
        ]
        controller.fleet_summaries.return_value = {}
        page = DashboardPage(controller)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        page.resize(1280, 900)
        page.refresh()
        page.show()
        for _ in range(3):
            self.app.processEvents()
        cards = page.findChildren(FleetParameterCard)
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(card.height() == 68 for card in cards))
        self.assertEqual(len({card.y() for card in cards}), 1)
        selected = []
        page.aircraft_selected.connect(selected.append)
        button = next(
            button for button in page.findChildren(QPushButton)
            if button.text().startswith('View Flights')
        )
        QTest.mouseClick(button, Qt.LeftButton)
        self.assertEqual(selected, ['test'])

    def test_metrics_are_beside_aircraft_identity_and_before_view_flights(self):
        controller = Mock()
        controller.list_aircraft.return_value = [
            Aircraft(id='test', registration='TEST', model='Bell 505',
                     serial_number='65000', flight_count=4),
        ]
        controller.fleet_summaries.return_value = {
            'test': {'avg_itt': 645.5, 'max_itt': 850.0},
        }
        page = DashboardPage(controller)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        page.resize(1215, 900)
        page.refresh()
        page.show()
        for _ in range(5):
            self.app.processEvents()
        cards = page.findChildren(FleetParameterCard)
        row = cards[0].parentWidget()
        identity = row.findChild(QWidget, 'fleetIdentity')
        button = next(
            widget for widget in row.findChildren(QPushButton)
            if widget.text().startswith('View Flights')
        )
        self.assertLess(identity.geometry().right(), cards[0].x())
        self.assertLess(cards[-1].geometry().right(), button.x())
        model = identity.findChild(QLabel, 'fleetModel')
        serial = identity.findChild(QLabel, 'fleetSerial')
        registration = identity.findChild(QLabel, 'fleetRegistration')
        count = identity.findChild(QLabel, 'fleetFlightCount')
        self.assertEqual(model.text(), 'Bell 505')
        self.assertEqual(serial.text(), 'SN 65000')
        self.assertLess(registration.geometry().bottom(), model.y())
        self.assertLess(model.geometry().bottom(), serial.y())
        self.assertEqual(serial.y(), count.y())
        self.assertEqual(serial.font().pixelSize(), model.font().pixelSize())
        self.assertEqual(
            len({widget.y() for widget in (identity, *cards, button)}), 1,
        )
        self.assertEqual(
            len({widget.height() for widget in (identity, *cards, button)}), 1,
        )
        self.assertEqual(
            len({widget.geometry().center().y() for widget in (*cards, button)}), 1,
        )
        self.assertLessEqual(
            abs(identity.geometry().center().y() - cards[0].geometry().center().y()), 1,
        )
        for left, right in zip(cards, cards[1:]):
            self.assertEqual(right.x() - left.geometry().right() - 1, 4)
        self.assertEqual(
            page.findChild(QScrollArea).horizontalScrollBar().maximum(), 0,
        )
        self.assertLess(row.height(), 110)
        self.assertEqual(
            [label.text() for label in cards[0].findChildren(QLabel, 'fleetParameterValue')],
            ['645.5', '850.0'],
        )


if __name__ == '__main__':
    unittest.main()
