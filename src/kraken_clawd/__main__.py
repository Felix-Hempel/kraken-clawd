"""Daemon: Hook-Server + Render-Schleife auf dem Kraken-LCD."""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from .lcd import Display
from .loop import run
from .server import HookServer
from .state import Store

log = logging.getLogger("kraken_clawd")


def main() -> int:
    logging.basicConfig(level=os.environ.get("CLAWD_LOG", "INFO"),
                        format="%(levelname)s %(name)s: %(message)s")
    store, lock, stop = Store(created=time.time()), threading.Lock(), threading.Event()
    try:
        server = HookServer(store, lock, port=int(os.environ.get("CLAWD_PORT", "7377")))
    except OSError as e:
        log.error("Hook-Port nicht verfügbar: %s", e)
        return 1
    server.start()
    display = Display()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        run(display, store, lock, stop)
    finally:
        server.stop()
        display.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
