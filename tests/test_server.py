import json
import threading
import urllib.request

import pytest

from kraken_clawd.server import HookServer


class FakeStore:
    def __init__(self):
        self.events = []

    def apply(self, ev, now):
        if ev.get("boom"):
            raise RuntimeError("kaputt")
        self.events.append((ev, now))


@pytest.fixture
def srv():
    store = FakeStore()
    s = HookServer(store, threading.Lock(), port=0, clock=lambda: 42.0)
    s.start()
    yield s, store
    s.stop()


def post(port, body: bytes, path="/hook"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.status, r.read()


def test_hook_is_applied(srv):
    s, store = srv
    status, body = post(s.port, json.dumps({"session_id": "a", "hook_event_name": "Stop"}).encode())
    assert (status, body) == (200, b"{}")
    assert store.events == [({"session_id": "a", "hook_event_name": "Stop"}, 42.0)]


@pytest.mark.parametrize("body", [b"kein json", b"[1,2]", b"\xff\xfe", b""])
def test_invalid_bodies_answer_200(srv, body):
    s, store = srv
    assert post(s.port, body)[0] == 200
    assert store.events == []


def test_store_exception_still_answers_200(srv):
    s, _ = srv
    assert post(s.port, b'{"boom": true}')[0] == 200
    assert post(s.port, b'{"session_id": "a", "hook_event_name": "Stop"}')[0] == 200


def test_other_paths_404(srv):
    s, _ = srv
    with pytest.raises(urllib.error.HTTPError) as e:
        post(s.port, b"{}", path="/x")
    assert e.value.code == 404


def test_binds_localhost_only(srv):
    s, _ = srv
    assert s._httpd.server_address[0] == "127.0.0.1"


def test_port_in_use_raises(srv):
    s, store = srv
    with pytest.raises(OSError):
        HookServer(store, threading.Lock(), port=s.port)
