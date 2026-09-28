"""Overview regression tests using synthetic flights, never the application DB."""

import os
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from helink.models.flight.alert import Alert
from helink.models.flight.engine_data import EngineData
from helink.models.flight.flight import Flight
from helink.models.flight.gps_data import GPSData
from helink.services.flight_overview_summary import (
    flight_parameter_statistics, important_flight_events, recorded_statistics,
)
from helink.services.flight_route_service import (
    flight_route_availability, route_coordinates,
)
from helink.ui.pages.flight_details_page import FlightDetailsPage
from helink.ui.tabs.alerts_tab import AlertsTab
from helink.ui.tabs.map_tab import OfflineRouteMap
from helink.ui.tabs.overview_tab import OverviewTab, PARAMETER_GROUPS
from helink.ui.theme import STYLE
from helink.ui.widgets import ImportedFilesList


def sample_flight():
    return Flight(
        id='test-flight', aircraft_id='test-aircraft', flight_date='2026-09-28',
        departure_time='11:00:00', arrival_time='11:10:00', duration='10 min',
        origin='LPBJ', destination='LPPT',
        imported_files=('1_Engine_Data_Recording', 'data_log',
                        '2_Exceedance_Log', '5_CAS'),
        engine_data=(
            EngineData(
                id=1, flight_id='test-flight', timestamp='2026-09-28 11:00:00',
                itt=640, eng_ot=80, xmsn_ot=60, oat=22,
                eng_op=95, xmsn_op=55, fuel_press=25,
                n1=90, n2=98, nr=100, tq=70,
            ),
            EngineData(
                id=2, flight_id='test-flight', timestamp='2026-09-28 11:10:00',
                itt=700, eng_ot=90, xmsn_ot=70, oat=24,
                eng_op=105, xmsn_op=65, fuel_press=30,
                n1=94, n2=100, nr=102, tq=80,
            ),
        ),
        data_log=(
            GPSData(id=1, flight_id='test-flight', timestamp='11:00:00',
                    latitude=38.0, longitude=-8.0, ias=100, alt_ind=1000),
            GPSData(id=2, flight_id='test-flight', timestamp='11:10:00',
                    latitude=38.1, longitude=-8.1, ias=120, alt_ind=2000),
        ),
        alerts=(
            Alert(id=1, flight_id='test-flight', kind='EXCEEDANCE',
                  alert_state='SET', alert_name='ITT', level='WARNING'),
            Alert(id=2, flight_id='test-flight', kind='EXCEEDANCE',
                  alert_state='CLEARED', alert_name='ITT', level='WARNING'),
            Alert(id=3, flight_id='test-flight', kind='CAS',
                  alert_state='SET', alert_name='MISCMP-P', level='CAUTION'),
            Alert(id=4, flight_id='test-flight', kind='CAS',
                  alert_state='CLEARED', alert_name='MISCMP-P', level='CAUTION'),
            Alert(id=5, flight_id='test-flight', kind='CAS',
                  alert_state='SET', alert_name='OTHER', level='WARNING'),
        ),
    )


class OverviewStatisticsTests(unittest.TestCase):
    def test_finite_values_only_and_zero_is_valid(self):
        values = (0, 10, None, float('nan'), float('inf'), 'invalid')
        result = recorded_statistics(
            [SimpleNamespace(value=value) for value in values], ('value',)
        )['value']
        self.assertEqual(result.samples, 2)
        self.assertEqual(result.average, 5)
        self.assertEqual(result.maximum, 10)

    def test_missing_values_are_not_zero(self):
        result = recorded_statistics([SimpleNamespace(value=None)], ('value',))
        self.assertIsNone(result['value'].average)
        self.assertIsNone(result['value'].maximum)
        self.assertEqual(result['value'].samples, 0)

    def test_statistics_cover_every_displayed_parameter(self):
        result = flight_parameter_statistics(sample_flight())
        keys = {key for _, specs in PARAMETER_GROUPS for key, *_ in specs}
        self.assertEqual(set(result), keys)
        self.assertEqual(len(keys), 13)
        self.assertEqual(result['itt'].average, 670)
        self.assertEqual(result['eng_ot'].maximum, 90)
        self.assertEqual(result['fuel_press'].average, 27.5)
        self.assertEqual(result['ias'].average, 110)
        self.assertEqual(result['alt_ind'].maximum, 2000)
        self.assertTrue(all(stat.samples == 2 for stat in result.values()))

    def test_counts_only_important_set_activations(self):
        result = important_flight_events(sample_flight())
        self.assertEqual(set(result), {'exceedances', 'miscmp'})
        self.assertEqual(result['exceedances'].count, 1)
        self.assertEqual(result['miscmp'].count, 1)
        self.assertEqual(result['exceedances'].activated_names, (('ITT', 1),))

    def test_activated_names_group_repeats_and_exclude_cleared_only_events(self):
        flight = sample_flight()
        extra = (
            replace(flight.alerts[0], id=6, alert_name=' itt '),
            replace(flight.alerts[0], id=7, alert_name='VNE'),
            replace(flight.alerts[1], id=8, alert_name='ENG OIL TEMP'),
        )
        result = important_flight_events(replace(flight, alerts=flight.alerts + extra))
        self.assertEqual(result['exceedances'].count, 3)
        self.assertEqual(
            result['exceedances'].activated_names, (('ITT', 2), ('VNE', 1)),
        )

    def test_miscmp_name_and_state_are_normalized_and_not_level_restricted(self):
        alert = Alert(
            id=1, flight_id='test-flight', kind='CAS', alert_state=' set ',
            alert_name=' miscmp-p ', level='WARNING',
        )
        flight = replace(sample_flight(), alerts=(alert,))
        self.assertEqual(important_flight_events(flight)['miscmp'].count, 1)

    def test_missing_event_source_is_distinct_from_zero_events(self):
        flight = Flight(id='empty', aircraft_id='test', flight_date='')
        self.assertFalse(important_flight_events(flight)['miscmp'].available)
        self.assertFalse(important_flight_events(flight)['exceedances'].available)
        flight = replace(flight, imported_files=('2_Exceedance_Log', '5_CAS'))
        self.assertTrue(important_flight_events(flight)['miscmp'].available)
        self.assertTrue(important_flight_events(flight)['exceedances'].available)
        self.assertEqual(important_flight_events(flight)['miscmp'].count, 0)


class FlightRouteAvailabilityTests(unittest.TestCase):
    def test_available_for_valid_positions_and_installed_map_assets(self):
        with patch(
            'helink.services.flight_route_service.offline_map_assets_available',
            return_value=True,
        ):
            self.assertTrue(flight_route_availability(sample_flight()).available)

    def test_single_valid_position_is_consultable_like_the_map_renderer(self):
        flight = replace(sample_flight(), data_log=(sample_flight().data_log[0],))
        with patch(
            'helink.services.flight_route_service.offline_map_assets_available',
            return_value=True,
        ):
            self.assertTrue(flight_route_availability(flight).available)
            self.assertIsNotNone(OfflineRouteMap._point(flight.data_log[0]))

    def test_missing_gps_data_is_unavailable_even_if_imported_flag_exists(self):
        flight = replace(sample_flight(), data_log=())
        result = flight_route_availability(flight)
        self.assertFalse(result.available)
        self.assertIn('No GPS data', result.reason)

    def test_missing_map_resources_are_unavailable(self):
        with patch(
            'helink.services.flight_route_service.offline_map_assets_available',
            return_value=False,
        ):
            result = flight_route_availability(sample_flight())
        self.assertFalse(result.available)
        self.assertIn('resources are missing', result.reason)

    def test_invalid_coordinates_are_rejected_consistently(self):
        for latitude, longitude in (
            (None, -8), (38, None), (0, 0), (50, -8),
            (38, -12), (float('nan'), -8), (38, float('inf')), ('invalid', -8),
        ):
            with self.subTest(latitude=latitude, longitude=longitude):
                gps = replace(
                    sample_flight().data_log[0],
                    latitude=latitude, longitude=longitude,
                )
                self.assertIsNone(route_coordinates(gps))
                self.assertIsNone(OfflineRouteMap._point(gps))
                flight = replace(sample_flight(), data_log=(gps,))
                result = flight_route_availability(flight)
                self.assertFalse(result.available)
                self.assertIn('No valid GPS coordinates', result.reason)

    def test_numeric_strings_and_coverage_edges_use_renderer_rules(self):
        for latitude, longitude in (('38.0', '-8.0'), (35, -11), (45, 5)):
            with self.subTest(latitude=latitude, longitude=longitude):
                gps = replace(
                    sample_flight().data_log[0],
                    latitude=latitude, longitude=longitude,
                )
                point = OfflineRouteMap._point(gps)
                self.assertEqual(
                    route_coordinates(gps), (point['lat'], point['lon']),
                )


class OverviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Offscreen Windows does not discover system fonts automatically.
        font = Path('C:/Windows/Fonts/segoeui.ttf')
        if os.name == 'nt' and font.exists():
            QFontDatabase.addApplicationFont(str(font))
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        assets = patch(
            'helink.services.flight_route_service.offline_map_assets_available',
            return_value=True,
        )
        assets.start()
        self.addCleanup(assets.stop)
        self.tab = OverviewTab()
        self.tab.resize(1280, 860)
        self.tab.load(sample_flight())
        self.tab.show()
        self.app.processEvents()

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def test_values_and_only_two_event_tiles(self):
        self.assertEqual(self.tab.metric_values['itt_avg'].text(), '670.0')
        self.assertEqual(self.tab.metric_values['itt_max'].text(), '700.0')
        self.assertEqual(self.tab.metric_values['ias_avg'].text(), '110.0')
        self.assertEqual(self.tab.metric_values['alt_ind_max'].text(), '2,000')
        self.assertEqual(set(self.tab.event_badges), {'exceedances', 'miscmp'})
        self.assertEqual(self.tab.event_values['exceedances'].text(), '1')
        self.assertEqual(self.tab.event_values['miscmp'].text(), '1')
        self.assertEqual(self.tab.summary_values['arrival'].text(), '11:10:00')
        self.assertEqual(self.tab.file_count.text(), '4 / 9')
        self.assertEqual(self.tab.event_notes['exceedances'].text(), 'ITT')
        self.assertLess(
            self.tab.event_badges['miscmp'].width(),
            self.tab.event_badges['exceedances'].width(),
        )
        self.assertLess(
            self.tab.event_badges['miscmp'].height(),
            self.tab.event_badges['exceedances'].height(),
        )

    def test_destination_is_aligned_directly_below_departure(self):
        departure = self.tab.summary_values['departure'].mapTo(self.tab, QPoint())
        destination = self.tab.summary_values['destination'].mapTo(self.tab, QPoint())
        self.assertEqual(destination.x(), departure.x())
        self.assertGreater(destination.y(), departure.y())

    def test_single_route_button_is_aligned_below_arrival(self):
        summary = self.tab.summary_values['arrival'].parentWidget()
        self.assertIs(self.tab.view_route_button.parentWidget(), summary)
        arrival = self.tab.summary_values['arrival'].mapTo(self.tab, QPoint())
        route = self.tab.view_route_button.mapTo(self.tab, QPoint())
        self.assertEqual(route.x(), arrival.x())
        self.assertGreater(route.y(), arrival.y())
        self.assertEqual(self.tab.view_route_button.text(), 'View Route')
        self.assertTrue(self.tab.view_route_button.isEnabled())
        titles = [label.text() for label in summary.findChildren(QLabel)]
        self.assertNotIn('Recording Coverage', titles)
        self.assertNotIn('RECORDING COVERAGE', titles)
        self.assertNotIn('FLIGHT ROUTE', titles)
        self.assertNotIn('Map available', titles)
        self.assertNotIn('Map unavailable', titles)
        self.assertFalse(any('samples' in text or 'points' in text for text in titles))

    def test_view_route_requests_navigation(self):
        received = []
        self.tab.route_requested.connect(lambda: received.append('route'))
        QTest.mouseClick(self.tab.view_route_button, Qt.LeftButton)
        self.assertEqual(received, ['route'])

    def test_route_unavailable_explains_reason_and_disables_navigation(self):
        self.tab.load(replace(sample_flight(), data_log=()))
        self.assertEqual(self.tab.view_route_button.text(), 'Route Unavailable')
        self.assertFalse(self.tab.view_route_button.isEnabled())
        self.assertIn('No GPS data', self.tab.view_route_button.toolTip())
        self.tab.load(sample_flight())
        self.assertEqual(self.tab.view_route_button.text(), 'View Route')
        self.assertTrue(self.tab.view_route_button.isEnabled())

    def test_route_with_invalid_gps_is_not_marked_as_available(self):
        invalid = replace(sample_flight().data_log[0], latitude=0, longitude=0)
        self.tab.load(replace(sample_flight(), data_log=(invalid,)))
        self.assertEqual(self.tab.view_route_button.text(), 'Route Unavailable')
        self.assertIn('No valid GPS coordinates', self.tab.view_route_button.toolTip())
        self.assertFalse(self.tab.view_route_button.isEnabled())

    def test_removed_explanatory_text_is_not_shown(self):
        texts = [label.text() for label in self.tab.findChildren(QLabel)]
        self.assertFalse(any('SET activations' in text for text in texts))
        self.assertFalse(any('AVG and MAX across' in text for text in texts))

    def test_compact_imported_files_omit_status_labels_but_preserve_all_types(self):
        content = self.tab.files.widget()
        for name in ('importedFileLoadedStatus', 'importedFileMissingStatus'):
            self.assertEqual(content.findChildren(QLabel, name), [])
        self.assertEqual(len(content.findChildren(QLabel, 'importedFileName')), 9)
        self.assertEqual(self.tab.findChild(QLabel, 'importedFilesCount').text(), '4 / 9')
        self.assertEqual(self.tab.files.parentWidget().width(), 285)
        # Flight-list popovers retain their existing status labels.
        regular = ImportedFilesList(('data_log',))
        self.addCleanup(regular.deleteLater)
        self.assertEqual(
            len(regular.widget().findChildren(QLabel, 'importedFileLoadedStatus')), 1,
        )
        self.assertEqual(
            len(regular.widget().findChildren(QLabel, 'importedFileMissingStatus')), 8,
        )

    def test_event_clicks_emit_the_requested_category(self):
        received = []
        self.tab.event_requested.connect(received.append)
        for key in ('exceedances', 'miscmp'):
            QTest.mouseClick(self.tab.event_badges[key], Qt.LeftButton)
        self.assertEqual(received, ['exceedances', 'miscmp'])

    def test_parameter_cards_are_clickable_and_labels_do_not_intercept_clicks(self):
        received = []
        self.tab.parameter_requested.connect(received.append)
        for key, button in self.tab.metric_tiles.items():
            with self.subTest(parameter=key):
                self.assertEqual(button.cursor().shape(), Qt.PointingHandCursor)
                self.assertTrue(all(
                    label.testAttribute(Qt.WA_TransparentForMouseEvents)
                    for label in button.findChildren(QLabel)
                ))
                self.assertIn('Telemetry', button.toolTip())
                QTest.mouseClick(button, Qt.LeftButton)
        self.assertEqual(received, list(self.tab.metric_tiles))

    def test_parameter_shortcut_navigates_to_focused_large_telemetry_chart(self):
        route = QWidget()
        route.load = Mock()
        with patch('helink.ui.pages.flight_details_page.MapTab', return_value=route):
            page = FlightDetailsPage(Mock(), Mock(), Mock())
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        page.resize(1280, 1000)
        page.telemetry.load(sample_flight())
        page.overview.load(sample_flight())
        page.show()
        self.app.processEvents()
        self.assertEqual(page.telemetry.instrument.rowCount(), 1)
        for key, title in (('itt', 'ITT'), ('oat', 'OAT'), ('ias', 'IAS')):
            with self.subTest(parameter=key):
                page.tabs.setCurrentWidget(page.overview)
                page.overview.metric_tiles[key].click()
                self.app.processEvents()
                self.assertIs(page.tabs.currentWidget(), page.telemetry)
                self.assertTrue(page.telemetry.combine_charts_button.isChecked())
                self.assertEqual(page.telemetry.chart_filter.selected_keys(), (key,))
                self.assertEqual(
                    set(page.telemetry.combined_plot.parameter_lines), {title},
                )
                self.assertFalse(page.telemetry.combined_card.isHidden())

    def test_loading_another_flight_clears_previous_values(self):
        self.tab.load(Flight(id='empty', aircraft_id='test', flight_date=''))
        self.assertTrue(all(label.text() == '\u2014'
                            for label in self.tab.metric_values.values()))
        self.assertEqual(self.tab.event_values['miscmp'].text(), '\u2014')
        self.assertFalse(self.tab.event_badges['miscmp'].isEnabled())
        self.assertTrue(self.tab.event_badges['miscmp'].isHidden())
        self.assertEqual(self.tab.event_notes['exceedances'].text(), 'No exceedance data')
        self.assertFalse(self.tab.event_badges['exceedances'].property('eventActive'))
        self.assertEqual(self.tab.file_count.text(), '0 / 9')

    def test_zero_miscmp_is_hidden_and_exceedances_remain_visible(self):
        self.tab.load(replace(sample_flight(), alerts=()))
        self.assertEqual(self.tab.event_values['miscmp'].text(), '0')
        self.assertTrue(self.tab.event_badges['miscmp'].isHidden())
        self.assertFalse(self.tab.event_badges['miscmp'].property('eventActive'))
        self.assertTrue(self.tab.event_badges['miscmp'].isEnabled())
        self.assertFalse(self.tab.event_badges['exceedances'].isHidden())
        self.assertEqual(self.tab.event_notes['exceedances'].text(), 'No exceedances recorded')
        self.tab.load(sample_flight())
        self.assertFalse(self.tab.event_badges['miscmp'].isHidden())

    def test_long_exceedance_list_wraps_without_clipping(self):
        flight = sample_flight()
        alerts = tuple(
            replace(flight.alerts[0], id=index, alert_name=f'ENGINE PARAMETER {index}')
            for index in range(20)
        )
        self.tab.load(replace(flight, alerts=alerts))
        for width in (1000, 1280, 1600):
            with self.subTest(width=width):
                self.tab.resize(width, 860)
                self.app.processEvents()
                note = self.tab.event_notes['exceedances']
                required = note.fontMetrics().boundingRect(
                    QRect(0, 0, note.contentsRect().width(), 10000),
                    Qt.TextWordWrap, note.text(),
                ).height()
                self.assertGreaterEqual(note.height(), required)
                badge = self.tab.event_badges['exceedances']
                bottom = note.mapTo(badge, QPoint(0, note.height())).y()
                self.assertLessEqual(bottom, badge.height())

    def test_metric_values_fit_at_multiple_window_widths(self):
        for width in (1000, 1280, 1600):
            with self.subTest(width=width):
                self.tab.resize(width, 860)
                self.app.processEvents()
                for label in self.tab.metric_values.values():
                    self.assertGreaterEqual(
                        label.width(), label.fontMetrics().horizontalAdvance(label.text())
                    )
                self.assertTrue(all(group['columns'] >= 2
                                    for group in self.tab.metric_groups))

    def test_parameter_buttons_fill_grid_cells_and_have_consistent_row_sizes(self):
        for width in (760, 1000, 1280, 1600):
            with self.subTest(width=width):
                self.tab.resize(width, 860)
                for _ in range(3):
                    self.app.processEvents()
                for group in self.tab.metric_groups:
                    grid = group['grid']
                    columns = group['columns']
                    for index, button in enumerate(group['tiles']):
                        row, column = divmod(index, columns)
                        self.assertIs(grid.itemAtPosition(row, column).widget(), button)
                    for start in range(0, len(group['tiles']), columns):
                        buttons = group['tiles'][start:start + columns]
                        widths = [button.width() for button in buttons]
                        heights = [button.height() for button in buttons]
                        self.assertLessEqual(max(widths) - min(widths), 1)
                        self.assertEqual(len(set(heights)), 1)
                        self.assertEqual(len({button.y() for button in buttons}), 1)
                        self.assertEqual(buttons[0].x(), grid.geometry().left())
                        if len(buttons) == columns:
                            self.assertEqual(
                                buttons[-1].geometry().right(), grid.geometry().right(),
                            )
                        for left, right in zip(buttons, buttons[1:]):
                            self.assertEqual(
                                right.x() - left.geometry().right() - 1, grid.spacing(),
                            )
                        value_tops = [
                            label.mapTo(button.parentWidget(), QPoint()).y()
                            for button in buttons
                            for label in button.findChildren(QLabel, 'overviewMetricValue')
                        ]
                        self.assertEqual(len(set(value_tops)), 1)

    def test_parameter_titles_wrap_without_clipping_in_narrow_view(self):
        self.tab.resize(760, 860)
        for _ in range(3):
            self.app.processEvents()
        for button in self.tab.metric_tiles.values():
            title = button.findChild(QLabel, 'overviewParameterTitle')
            required = title.fontMetrics().boundingRect(
                QRect(0, 0, title.contentsRect().width(), 10000),
                Qt.TextWordWrap, title.text(),
            ).height()
            self.assertGreaterEqual(title.height(), required)
            for label in button.findChildren(QLabel):
                bottom = label.mapTo(button, QPoint(0, label.height())).y()
                self.assertLessEqual(bottom, button.height())

    def test_event_navigation_resets_stale_search_and_scopes_cas(self):
        cas = AlertsTab('CAS')
        self.addCleanup(cas.deleteLater)
        cas.load(sample_flight())
        cas.search.setText('unrelated previous search')
        cas.level.setCurrentText('WARNING')
        tabs = Mock()
        page = SimpleNamespace(cas=cas, exceed=Mock(), tabs=tabs)
        FlightDetailsPage.open_event_summary(page, 'miscmp')
        self.assertEqual(cas.search.text(), '')
        self.assertEqual(cas.level.currentText(), 'All')
        self.assertEqual(cas.alert_filter.currentText(), 'MISCMP-P')
        self.assertEqual(cas.table.rowCount(), 2)
        tabs.setCurrentWidget.assert_called_with(cas)
        FlightDetailsPage.open_event_summary(page, 'exceedances')
        page.exceed.set_filters.assert_called_once_with()
        tabs.setCurrentWidget.assert_called_with(page.exceed)

    def test_zero_miscmp_does_not_open_unrelated_alerts(self):
        cas = AlertsTab('CAS')
        self.addCleanup(cas.deleteLater)
        flight = replace(sample_flight(), alerts=(sample_flight().alerts[-1],))
        cas.load(flight)
        cas.set_filters('All', 'MISCMP-P')
        self.assertEqual(cas.alert_filter.currentText(), 'MISCMP-P')
        self.assertEqual(cas.table.rowCount(), 0)

    def test_miscmp_navigation_matches_normalized_names(self):
        cas = AlertsTab('CAS')
        self.addCleanup(cas.deleteLater)
        alert = replace(sample_flight().alerts[2], alert_name=' miscmp-p ')
        cas.load(replace(sample_flight(), alerts=(alert,)))
        cas.set_filters('All', 'MISCMP-P')
        self.assertEqual(cas.table.rowCount(), 1)
        self.assertEqual(cas.alert_filter.currentText(), ' miscmp-p ')


if __name__ == '__main__':
    unittest.main()
