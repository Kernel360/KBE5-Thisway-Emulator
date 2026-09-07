"""Clock/payload regressions. No live backend, route API, singleton startup or device files."""
import ast
import contextlib
import io
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, mock_open, patch

from models.emulator_data import GpsLogRequest, GpsLogItem, PowerLogRequest, GeofenceLogRequest
from services.emulator_manager import EmulatorManager
from services.log_generators.gps_log_generator import GpsLogGenerator
from services.log_generators.power_log_generator import PowerLogGenerator
from services.log_generators.geofence_log_generator import GeofenceLogGenerator
from services.log_handlers.gps_log_handler import GpsLogHandler, KST, gps_timestamp
from services.log_handlers.power_log_handler import PowerLogHandler
from services.log_handlers.geofence_log_handler import GeofenceLogHandler

ROOT = Path(__file__).resolve().parents[1]
MDN = "fixture-mdn"


def load_definition(path, name, namespace=None):
    """Execute the real definition without the module's global network/thread singletons."""
    tree = ast.parse((ROOT / path).read_text())
    definition = next(node for node in tree.body if getattr(node, "name", None) == name)
    module = ast.Module(body=[definition], type_ignores=[])
    scope = dict(globals())
    scope.update(namespace or {})
    exec(compile(module, str(ROOT / path), "exec"), scope)
    return scope[name]


def manager_fixture():
    emulator = {"last_latitude": 37.123456, "last_longitude": 127.123456, "is_active": True}
    manager = Mock()
    manager.active_emulators = {MDN: emulator}
    manager.is_emulator_active.return_value = True
    manager.get_emulator_dict.return_value = emulator
    manager.get_accumulated_distance.return_value = 100
    manager.last_gps_batch_data = None
    manager.collecting_data = []
    manager.last_power_on_time = ""
    manager.last_positions = {}
    manager.kakao_route_points = []
    manager.current_route_index = 0
    return manager


def points(start, count):
    return [{"timestamp": start + timedelta(seconds=i), "latitude": 37.123456 + i * .000001,
             "longitude": 127.123456, "speed": 1, "angle": 0, "battery": 90} for i in range(count)]


def wire_times(packets):
    return [datetime.strptime(packet.oTime[:10] + f"{int(item.min):02d}{int(item.sec):02d}", "%Y%m%d%H%M%S").replace(tzinfo=KST)
            for packet in packets for item in packet.cList]


class GpsTimeGroupingTest(unittest.TestCase):
    def setUp(self):
        self.manager = manager_fixture()
        self.generator = GpsLogGenerator(self.manager)
        self.stdout = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.stdout)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_midnight_preserves_source_date_minute_second_and_all_points(self):
        source = points(datetime(2026, 9, 6, 23, 59, 58), 5)
        packets = self.generator.create_gps_log_from_collected_data(MDN, source)
        self.assertEqual(["2", "3"], [p.cCnt for p in packets])
        self.assertEqual([gps_timestamp(p["timestamp"]) for p in source], wire_times(packets))
        self.assertEqual([str(int(round(p["latitude"], 6) * 1000000)) for p in source], [i.lat for p in packets for i in p.cList])
        distances = [int(i.sum) for p in packets for i in p.cList]
        self.assertEqual(sorted(distances), distances)
        self.manager.update_accumulated_distance.assert_called_once_with(distances[-1], MDN)

    def test_minute_boundary_stays_one_packet_with_per_item_minutes(self):
        source = points(datetime(2026, 9, 7, 10, 58, 58, tzinfo=KST), 4)
        packets = self.generator.create_gps_log_from_collected_data(MDN, source)
        self.assertEqual(1, len(packets))
        self.assertEqual([p["timestamp"] for p in source], wire_times(packets))

    def test_aware_utc_is_converted_and_naive_is_explicitly_kst(self):
        source = points(datetime(2026, 9, 6, 14, 59, 59, tzinfo=timezone.utc), 2)
        packets = self.generator.create_gps_log_from_collected_data(MDN, source)
        self.assertEqual(["20260906235959", "20260907000000"], [p.oTime for p in packets])
        self.assertEqual(datetime(2026, 9, 7, 0, 0, tzinfo=KST), gps_timestamp(datetime(2026, 9, 7)))

    def test_same_hour_six_hundred_item_limit_has_no_loss(self):
        source = points(datetime(2026, 9, 7, 10, 0, tzinfo=KST), 601)
        packets = self.generator.create_gps_log_from_collected_data(MDN, source)
        self.assertEqual(["600", "1"], [p.cCnt for p in packets])
        self.assertEqual([p["timestamp"] for p in source], wire_times(packets))

    def test_invalid_source_clock_fails_before_distance_mutation(self):
        for invalid in (None, "20260907100000"):
            with self.subTest(invalid=invalid):
                source = points(datetime(2026, 9, 7), 2)
                source[1]["timestamp"] = invalid
                with self.assertRaises(ValueError):
                    self.generator.create_gps_log_from_collected_data(MDN, source)
        self.manager.update_accumulated_distance.assert_not_called()

    def test_handler_batch_uses_source_clock_and_terminal_fields(self):
        source = points(datetime(2026, 9, 6, 23, 59, 59), 2)
        for point in source:
            point.update(gcd="A", heading=0, accumulated_distance=100, battery_level=90)
        packets = GpsLogHandler().batch_gps_data_points(MDN, source, {"terminal_id": "FIXTURE", "manufacture_id": 6, "packet_version": 5, "device_id": 1})
        self.assertEqual(2, len(packets))
        self.assertTrue(all(p.tid == "FIXTURE" for p in packets))
        self.assertEqual([gps_timestamp(p["timestamp"]) for p in source], wire_times(packets))

    def test_handler_attempts_every_packet_even_when_first_store_fails(self):
        packets = self.generator.create_gps_log_from_collected_data(MDN, points(datetime(2026, 9, 6, 23, 59, 59), 2))
        handler = GpsLogHandler()
        with patch.object(handler, "store_log", side_effect=[False, True]) as store:
            self.assertFalse(handler.store_gps_log(MDN, packets))
        self.assertEqual(packets, [c.args[1] for c in store.call_args_list])

    def test_realtime_and_process_facade_forward_all_packets(self):
        facade_type = load_definition("services/data_generator.py", "EmulatorDataGenerator")
        facade = facade_type.__new__(facade_type)
        facade.emulator_manager = self.manager
        facade.gps_generator = self.generator
        facade.log_storage_manager = Mock()
        facade.log_storage_manager.count_pending_logs.return_value = {"gps": 0, "power": 0, "geofence": 0}
        handler = GpsLogHandler()
        facade.log_storage_manager.store_gps_log.side_effect = handler.store_gps_log
        source = points(datetime(2026, 9, 6, 23, 59, 59), 2)
        with patch.object(handler, "store_log", return_value=True) as store:
            packets = facade._process_collected_data(MDN, source)
            self.assertEqual(packets, [c.args[1] for c in store.call_args_list])
            store.reset_mock()
            self.assertTrue(facade.process_gps_log(packets))
            self.assertEqual(packets, [c.args[1] for c in store.call_args_list])
            store.reset_mock()
            self.assertTrue(facade.store_unsent_log(MDN, packets))
            self.assertEqual(packets, [c.args[1] for c in store.call_args_list])

    def test_manual_cli_stores_all_generated_packets(self):
        packets = self.generator.create_gps_log_from_collected_data(MDN, points(datetime(2026, 9, 6, 23, 59, 59), 2))
        facade = Mock()
        facade.generate_gps_log.return_value = packets
        cli_type = load_definition("main.py", "EmulatorCLI", {"data_generator": facade})
        cli = cli_type()
        self.assertTrue(cli.generate_gps_log(MDN))
        facade.store_gps_log.assert_called_once_with(MDN, packets)
        self.assertIn("2개 항목", self.stdout.getvalue())

    def test_manual_fixture_script_handles_a_split_sixty_point_batch(self):
        packets = self.generator.create_gps_log_from_collected_data(MDN, points(datetime(2026, 9, 6, 23, 59, 58), 60))
        facade = Mock()
        facade.generate_gps_log.return_value = packets
        facade.get_unsent_logs.return_value = packets
        facade.emulator_manager.data_timer = True
        facade.emulator_manager.stop_realtime_data_collection.side_effect = lambda: setattr(facade.emulator_manager, "data_timer", None)
        fixture = load_definition("test_emulator.py", "test_emulator", {"data_generator": facade, "time": Mock()})
        self.assertTrue(fixture())
        facade.store_gps_log.assert_called_once_with("01012345678", packets)

    def test_new_power_geofence_and_route_clocks_request_kst(self):
        fixed = datetime(2026, 9, 6, 15, 1, tzinfo=timezone.utc)
        for module, produce in [
            ("services.log_generators.power_log_generator", lambda: PowerLogGenerator(self.manager).generate_power_log(MDN)),
            ("services.log_generators.geofence_log_generator", lambda: GeofenceLogGenerator(self.manager).generate_geofence_log(MDN, "1", "1")),
            ("services.log_generators.gps_log_generator", lambda: self.generator._convert_route_to_collected_data(points(fixed, 1))),
        ]:
            with self.subTest(module=module), patch(module + ".datetime") as clock:
                clock.now.side_effect = lambda tz=None: fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
                output = produce()
                clock.now.assert_called_once_with(KST)
                observed = output[0]["timestamp"].strftime("%Y%m%d%H%M%S") if isinstance(output, list) else getattr(output, "oTime", None) or output.onTime
                self.assertEqual("20260907000100", observed)

    def test_unknown_on_time_does_not_invent_an_hour_long_trip(self):
        self.assertIsNone(PowerLogGenerator(self.manager).generate_power_log(MDN, power_on=False))
        self.manager.update_accumulated_distance.assert_not_called()
        self.assertEqual({}, self.manager.last_positions)

    def test_realtime_worker_produces_aware_kst_observation(self):
        manager = EmulatorManager.__new__(EmulatorManager)
        manager.mdn, manager.is_active = MDN, True
        manager.last_latitude, manager.last_longitude = 37.123456, 127.123456
        manager.collecting_data = []
        manager.update_position = Mock()
        manager.data_callback = Mock()
        stop = threading.Event()
        fixed = datetime(2026, 9, 6, 15, 1, tzinfo=timezone.utc)
        with patch("services.emulator_manager.datetime") as clock, patch("services.emulator_manager.time.sleep", side_effect=lambda _: stop.set()):
            clock.now.side_effect = lambda tz=None: fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
            manager._data_collection_worker(1, 1, 60, stop)
        self.assertEqual(3, clock.now.call_count)
        self.assertTrue(all(call.args == (KST,) for call in clock.now.call_args_list))
        data = manager.data_callback.call_args.args[1]
        self.assertEqual(fixed.astimezone(KST), data[0]["timestamp"])

    def test_route_failure_and_debug_handlers_do_not_print_raw_key_or_coordinates(self):
        secret = "fixture-secret-do-not-log"
        with patch("builtins.open", mock_open(read_data='{"kakao_api_key":"' + secret + '"}')), patch("services.log_generators.gps_log_generator.requests.get", side_effect=RuntimeError(secret + " 37.123456 127.123456")) as request:
            self.assertIsNone(self.generator._get_kakao_route((37.123456, 127.123456), (37.654321, 127.654321)))
            self.assertEqual((3, 5), request.call_args.kwargs["timeout"])
        packets = self.generator.create_gps_log_from_collected_data(MDN, points(datetime(2026, 9, 7), 1))
        power = PowerLogGenerator(self.manager).generate_power_log(MDN)
        geofence = GeofenceLogGenerator(self.manager).generate_geofence_log(MDN, "1", "1")
        for handler, packet in [(GpsLogHandler(), packets[0]), (PowerLogHandler(), power), (GeofenceLogHandler(), geofence)]:
            handler._print_debug_log(packet)
            with patch.object(handler, "store_log", return_value=True):
                getattr(handler, "store_" + handler.log_type + "_log")(MDN, packet)
        output = self.stdout.getvalue()
        for sensitive in (secret, "37.123456", "127.123456", "37123456", "127123456"):
            self.assertNotIn(sensitive, output)


if __name__ == "__main__":
    unittest.main()
