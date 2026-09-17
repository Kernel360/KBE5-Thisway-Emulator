import contextlib
import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from services.device_credentials import device_headers
from services.device_credentials import load_device_credential
from services.log_storage_manager import LogStorageManager
from services.log_handlers.gps_log_handler import GpsLogHandler
from services.log_handlers.power_log_handler import PowerLogHandler
from services.log_handlers.geofence_log_handler import GeofenceLogHandler


class DeviceAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "credentials.json"
        self.key = "twdev_" + "A" * 43
        self.write_key(self.key)
        self.env = patch.dict(os.environ, {"DEVICE_CREDENTIALS_FILE": str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.received = []
        self.status = 200
        self.on_request = None
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.received.append((self.path, dict(self.headers), body))
                if test.on_request:
                    test.on_request()
                self.send_response(test.status)
                if test.status == 302:
                    self.send_header("Location", "/redirect-target")
                self.end_headers()
                self.wfile.write(b'{"code":"000"}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def write_key(self, key, device_id=123):
        self.path.write_text(json.dumps({"fixture": {"device_id": device_id, "key": key}}))
        self.path.chmod(0o600)

    def packets(self):
        common = dict(mdn="fixture", tid="1", mid="1", pv="1", did="1", gcd="A",
                      lat="37000000", lon="127000000", ang="0", spd="0", sum="100")
        return [
            (GpsLogHandler(backend_url=self.url), GpsLogRequest(**common, oTime="20200101102000", cCnt="1",
                 cList=[dict(sec="30", gcd="A", lat="37000000", lon="127000000", ang="0", spd="0", sum="100", bat="12")])),
            (PowerLogHandler(backend_url=self.url), PowerLogRequest(**common, onTime="20200101102000")),
            (GeofenceLogHandler(backend_url=self.url), GeofenceLogRequest(**common, oTime="20200101102000", geoGrpId="1", geoPId="1", evtVal="1")),
        ]

    def test_three_real_http_requests_use_device_headers_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for handler, packet in self.packets():
                self.assertEqual(handler.send_log_to_backend(packet), (True, "Success"))
        self.assertEqual(len(self.received), 3)
        self.assertEqual(len({headers["X-Request-Id"] for _, headers, _ in self.received}), len(self.received))
        for _, headers, body in self.received:
            self.assertEqual(headers["X-Device-Id"], "123")
            self.assertEqual(headers["X-Device-Key"], self.key)
            self.assertRegex(headers["X-Request-Id"], r"^[0-9a-f-]{36}$")
            self.assertRegex(headers["X-Request-Timestamp"], r"^[0-9]{10}$")
            self.assertNotIn("Authorization", headers)
            self.assertNotIn(self.key, json.dumps(body))
        self.assertNotIn(self.key, output.getvalue())

    def test_missing_or_other_mdn_credentials_fail_without_network(self):
        handler, packet = self.packets()[0]
        self.path.write_text("{}")
        self.assertFalse(handler.send_log_to_backend(packet)[0])
        self.path.unlink()
        self.assertFalse(handler.send_log_to_backend(packet)[0])
        self.assertEqual(self.received, [])

    def test_file_permission_and_key_shape_are_checked(self):
        handler, packet = self.packets()[0]
        self.path.chmod(0o644)
        self.assertFalse(handler.send_log_to_backend(packet)[0])
        self.write_key("Bearer secret")
        self.assertFalse(handler.send_log_to_backend(packet)[0])
        self.assertEqual(self.received, [])

    def test_key_rotation_is_loaded_on_the_next_send(self):
        handler, packet = self.packets()[0]
        self.assertTrue(handler.send_log_to_backend(packet)[0])
        replacement = "twdev_" + "B" * 43
        self.write_key(replacement)
        self.assertTrue(handler.send_log_to_backend(packet)[0])
        self.assertEqual(self.received[-1][1]["X-Device-Key"], replacement)

    def test_redirect_is_not_followed(self):
        self.status = 302
        handler, packet = self.packets()[0]
        self.assertFalse(handler.send_log_to_backend(packet)[0])
        self.assertEqual(len(self.received), 1)

    def test_auth_rejection_is_queued_without_recursive_lock_or_secret(self):
        self.status = 401
        handler, packet = self.packets()[0]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            worker = threading.Thread(target=lambda: handler.store_log("fixture", packet), daemon=True)
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive(), "store_log must not reacquire queue_lock")
        self.assertEqual(handler.count_pending_logs("fixture"), 1)
        self.assertNotIn(self.key, repr(handler.get_pending_logs("fixture")))
        self.assertNotIn(self.key, output.getvalue())

    def test_external_plaintext_or_embedded_secrets_are_rejected(self):
        for url in ("http://example.test", "https://user:password@example.test", "https://example.test?key=value"):
            with self.assertRaises(ValueError):
                device_headers("fixture", url)
        self.assertEqual(device_headers("fixture", "https://example.test")["X-Device-Id"], "123")

    def test_failed_backlog_is_paused_when_same_mdn_uses_a_replacement_key_file(self):
        self.status = 503
        packets = self.packets()
        original_bodies = [packet.model_dump() for _, packet in packets]
        output = io.StringIO()
        replacement = "twdev_" + "B" * 43
        old_fingerprint = hashlib.sha256(self.key.encode()).hexdigest()
        new_fingerprint = hashlib.sha256(replacement.encode()).hexdigest()
        with contextlib.redirect_stdout(output):
            for handler, packet in packets:
                handler.store_log("fixture", packet)
            self.received.clear()
            replacement_file = Path(self.temp.name) / "replacement.json"
            replacement_file.write_text(json.dumps({"fixture": {"device_id": 123, "key": replacement}}))
            replacement_file.chmod(0o600)
            os.environ["DEVICE_CREDENTIALS_FILE"] = str(replacement_file)
            self.status = 200
            for (handler, _), original in zip(packets, original_bodies):
                self.assertEqual(handler.process_pending_logs("fixture"), 0)
                retained = handler.get_pending_logs("fixture")
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0]["retry_state"], "paused")
                self.assertEqual(retained[0]["pause_reason"], "credential_changed")
                self.assertEqual(retained[0]["data"].model_dump(), original)
                self.assertEqual(retained[0]["retry_count"], 0)
                self.assertNotIn(old_fingerprint, repr(retained))
                self.assertNotIn(self.key, repr(retained))
        self.assertEqual(self.received, [])
        for sensitive in (self.key, replacement, old_fingerprint, new_fingerprint, "37000000", "127000000"):
            self.assertNotIn(sensitive, output.getvalue())

    def test_same_credential_retries_preserve_original_events_and_make_fresh_request_ids(self):
        self.status = 503
        packets = self.packets()
        original_bodies = [packet.model_dump() for _, packet in packets]
        for handler, packet in packets:
            handler.store_log("fixture", packet)
        initial_ids = {headers["X-Request-Id"] for _, headers, _ in self.received}
        self.received.clear()
        self.status = 200
        # Mutating the producer's object must not rewrite already queued source events.
        packets[0][1].oTime = "20250101102000"
        packets[0][1].cList[0].sec = "59"
        for handler, _ in packets:
            self.assertEqual(handler.process_pending_logs("fixture"), 1)
            self.assertEqual(handler.count_pending_logs("fixture"), 0)
        self.assertEqual([body for _, _, body in self.received], original_bodies)
        self.assertTrue(initial_ids.isdisjoint({headers["X-Request-Id"] for _, headers, _ in self.received}))

    def test_initially_unknown_identity_remains_paused_after_a_key_is_supplied(self):
        packets = self.packets()
        self.path.unlink()
        for handler, packet in packets:
            handler.store_log("fixture", packet)
            self.assertEqual(handler.get_pending_logs("fixture")[0]["pause_reason"], "source_identity_unknown")
            self.assertIsNone(handler.get_pending_logs("fixture")[0]["source_binding"])
        self.write_key(self.key)
        for handler, _ in packets:
            self.assertEqual(handler.process_pending_logs("fixture"), 0)
            self.assertEqual(handler.count_pending_logs("fixture"), 1)
        self.assertEqual(self.received, [])

    def test_device_id_change_is_paused_even_if_key_text_is_unchanged(self):
        self.status = 401
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        self.received.clear()
        self.write_key(self.key, device_id=456)
        self.status = 200
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(handler.get_pending_logs("fixture")[0]["pause_reason"], "credential_changed")
        self.assertEqual(self.received, [])

    def test_first_send_and_queue_use_the_same_snapshot_when_file_rotates_during_http(self):
        self.status = 503
        replacement = "twdev_" + "B" * 43
        self.on_request = lambda: self.write_key(replacement)
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        retained = handler.get_pending_logs("fixture")[0]
        self.assertEqual(retained["source_binding"].fingerprint, hashlib.sha256(self.key.encode()).hexdigest())
        self.received.clear()
        self.on_request = None
        self.status = 200
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(self.received, [])

    def test_retry_sends_the_compared_snapshot_without_loading_a_new_key_after_validation(self):
        self.status = 503
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        self.received.clear()
        self.status = 200

        def load_then_rotate(*args):
            snapshot = load_device_credential(*args)
            self.write_key("twdev_" + "B" * 43)
            return snapshot

        with patch("services.log_handlers.base_log_handler.load_device_credential", side_effect=load_then_rotate) as load:
            self.assertEqual(handler.process_pending_logs("fixture"), 1)
            self.assertEqual(load.call_count, 1)
        self.assertEqual(self.received[0][1]["X-Device-Key"], self.key)

    def test_review_pause_is_sticky_and_retained_past_normal_expiry(self):
        self.status = 503
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        self.write_key("twdev_" + "B" * 43)
        retained = handler.pending_logs["fixture"].queue[0]
        retained["timestamp"] = datetime.now() - timedelta(days=2)
        self.received.clear()
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.write_key(self.key)
        self.status = 200
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(handler.count_pending_logs("fixture"), 1)
        self.assertEqual(handler.get_pending_logs("fixture")[0]["retry_state"], "paused")
        self.assertEqual(self.received, [])

    def test_legacy_queue_identity_is_not_inferred_from_the_current_file(self):
        self.status = 503
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        retained = handler.pending_logs["fixture"].queue[0]
        del retained["source_binding"]
        self.received.clear()
        self.status = 200
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(handler.get_pending_logs("fixture")[0]["pause_reason"], "source_identity_unknown")
        self.assertEqual(self.received, [])

    def test_known_queue_pauses_when_current_credential_cannot_be_verified(self):
        self.status = 503
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        self.received.clear()
        self.path.unlink()
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(handler.get_pending_logs("fixture")[0]["pause_reason"], "credential_unavailable")
        self.assertEqual(handler.count_pending_logs("fixture"), 1)
        self.assertEqual(self.received, [])

    def test_normal_matching_pending_rows_keep_the_existing_expiry_policy(self):
        self.status = 503
        handler, packet = self.packets()[0]
        handler.store_log("fixture", packet)
        handler.pending_logs["fixture"].queue[0]["timestamp"] = datetime.now() - timedelta(days=2)
        self.received.clear()
        self.assertEqual(handler.process_pending_logs("fixture"), 0)
        self.assertEqual(handler.count_pending_logs("fixture"), 0)
        self.assertEqual(self.received, [])

    def test_manager_counts_queue_objects_and_includes_paused_review_items(self):
        self.path.unlink()
        packets = self.packets()
        for handler, packet in packets:
            handler.store_log("fixture", packet)
        # Construct only the counting boundary: no background sender or config-file side effects.
        manager = object.__new__(LogStorageManager)
        manager.gps_handler, manager.power_handler, manager.geofence_handler = [handler for handler, _ in packets]
        self.assertEqual(manager.count_pending_logs(), {"gps": 1, "power": 1, "geofence": 1})


if __name__ == "__main__":
    unittest.main()
