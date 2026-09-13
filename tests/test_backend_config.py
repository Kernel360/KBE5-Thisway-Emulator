"""Backend startup must enforce the same destination policy as telemetry sends."""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from services.log_storage_manager import LogStorageManager, get_backend_url


class BackendConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.json"
        self.config.write_text("{}")
        self.env = patch.dict(os.environ, {"CONFIG_PATH": str(self.config), "BACKEND_URL": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_invalid_destinations_fail_before_startup_network_and_are_not_logged(self):
        invalid_urls = (
            "https://operator:fixture-secret@example.test",
            "https://example.test?key=fixture-secret",
            "https://example.test/#fixture-secret",
            "http://example.test",
            "https://example.test:invalid",
            "https://[malformed-fixture-secret",
        )
        for source in ("config", "environment"):
            for url in invalid_urls:
                with self.subTest(source=source, url=url):
                    self.config.write_text(json.dumps({"backend_url": url} if source == "config" else {}))
                    os.environ["BACKEND_URL"] = url if source == "environment" else ""
                    with patch("requests.get") as send:
                        with self.assertRaises(ValueError) as raised:
                            LogStorageManager()
                        send.assert_not_called()
                    self.assertNotIn("fixture-secret", str(raised.exception))
        self.assertNotIn("fixture-secret", self.output.getvalue())

    def test_config_precedence_and_loopback_default_are_preserved(self):
        self.assertEqual("http://localhost:8080", get_backend_url())
        os.environ["BACKEND_URL"] = "https://environment.example.test/"
        self.assertEqual("https://environment.example.test", get_backend_url())
        self.config.write_text(json.dumps({"backend_url": "http://127.0.0.1:18080/"}))
        self.assertEqual("http://127.0.0.1:18080", get_backend_url())

    def test_health_probe_uses_public_contract_and_does_not_follow_redirects(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.path, dict(self.headers)))
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        os.environ["BACKEND_URL"] = f"http://127.0.0.1:{server.server_port}/"
        manager = LogStorageManager()
        self.assertEqual(["/api/health"], [path for path, _ in received])
        self.assertNotIn("Authorization", received[0][1])
        self.assertNotIn("X-Device-Key", received[0][1])
        self.assertEqual("Connected (Abnormal: 302)", manager.backend_connection_status)
        self.assertFalse(manager.running)

    def test_health_failure_does_not_expose_exception_text_in_logs_or_status(self):
        with patch("requests.get", side_effect=requests.ConnectionError("fixture-secret")):
            manager = LogStorageManager()
        self.assertEqual("Connection Failed", manager.backend_connection_status)
        self.assertNotIn("fixture-secret", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
