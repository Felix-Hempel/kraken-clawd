"""Mini-HTTP-Server: nimmt Claude-Code-Hooks (type "http") an und reicht sie an den Store."""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

log = logging.getLogger(__name__)
MAX_BODY = 1 << 20


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_port = False   # zweiter Daemon auf demselben Port muss scheitern


class HookServer:
    def __init__(self, store, lock: threading.Lock, host: str = "127.0.0.1", port: int = 7377,
                 clock: Callable[[], float] = time.time):
        self._httpd = _Server((host, port), _handler(store, lock, clock))
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="hooks", daemon=True)

    def start(self) -> None:
        self._thread.start()
        log.info("Hooks auf http://127.0.0.1:%d/hook", self.port)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def _handler(store, lock: threading.Lock, clock: Callable[[], float]):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/hook":
                self.send_response(404)
                self.end_headers()
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if 0 < length <= MAX_BODY:
                self._apply(self.rfile.read(length))
            else:
                self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def _apply(self, raw: bytes) -> None:
            try:
                ev = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                log.debug("ungültiges Hook-JSON ignoriert")
                return
            if not isinstance(ev, dict):
                return
            try:
                with lock:
                    store.apply(ev, clock())
            except Exception:
                log.exception("Hook-Verarbeitung fehlgeschlagen: %s", ev.get("hook_event_name"))

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

    return Handler
