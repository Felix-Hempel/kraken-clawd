from types import SimpleNamespace

from liquidctl.driver.kraken3 import KrakenZ3
from PIL import Image

from kraken_clawd.lcd import Display, to_rgb565


class FakeDev:
    description = "NZXT Kraken 2023"

    def __init__(self, fast_error=None):
        self.calls = []
        self._fw = (2, 0, 0)
        self.orientation = 0
        self.broken = False
        self.fast_error = fast_error

    def connect(self):
        self.calls.append("connect")

    def initialize(self):
        self.calls.append("init")

    def disconnect(self):
        self.calls.append("disconnect")

    def set_screen(self, channel, mode, value):
        if self.broken:
            raise OSError("usb weg")
        self.calls.append(("screen", mode, value))

    def _send_2023_data_fw2(self, data, info):
        if self.broken:
            raise OSError("usb weg")
        if self.fast_error:
            raise self.fast_error
        self.calls.append(("fast", len(data), info))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def img(color=(155, 107, 255)):
    return Image.new("RGB", (240, 240), color)


def test_rgb565_matches_liquidctl(tmp_path):
    src = Image.effect_noise((240, 240), 80).convert("RGB")
    path = tmp_path / "n.png"
    src.save(path)
    fake_self = SimpleNamespace(lcd_resolution=(240, 240))
    expected = bytes(KrakenZ3._prepare_static_file_rgb16(fake_self, str(path), 1))
    assert to_rgb565(src, 1) == expected


def test_first_frame_public_then_fast_path(tmp_path):
    dev = FakeDev()
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    d.show(img())
    d.show(img())
    assert dev.calls[:2] == ["connect", "init"]
    assert dev.calls[2][:2] == ("screen", "static")
    assert dev.calls[3][0] == "fast" and dev.calls[3][1] == 240 * 240 * 2
    assert dev.calls[3][2] == [0x06, 0, 0, 0] + list((240 * 240 * 2).to_bytes(4, "little"))


def test_falls_back_when_private_api_changed(tmp_path):
    dev = FakeDev(fast_error=TypeError("signatur geändert"))
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    for _ in range(3):
        d.show(img())
    screens = [c for c in dev.calls if isinstance(c, tuple) and c[0] == "screen"]
    assert len(screens) == 3
    assert "disconnect" not in dev.calls


def test_usb_error_reconnects_with_backoff(tmp_path):
    dev, clock, finds = FakeDev(), Clock(), []
    d = Display(finder=lambda: finds.append(1) or [dev], clock=clock, tmp=tmp_path / "f.png")
    d.show(img())
    d.show(img())
    dev.broken = True
    d.show(img())                       # Fehler -> getrennt, nächster Versuch in 1 s
    assert "disconnect" in dev.calls
    dev.broken = False
    d.show(img())
    assert len(finds) == 1              # noch im Backoff
    clock.t = 1.1
    d.show(img())
    assert len(finds) == 2


def test_missing_device_never_raises(tmp_path):
    clock = Clock()
    d = Display(finder=lambda: [], clock=clock, tmp=tmp_path / "f.png")
    d.show(img())
    d.brightness(50)
    clock.t = 100
    d.show(img())
    d.close()


def test_brightness_only_sent_on_change(tmp_path):
    dev = FakeDev()
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    for pct in (100, 100, 20, 20):
        d.brightness(pct)
    assert [c for c in dev.calls if isinstance(c, tuple) and c[1] == "brightness"] == [
        ("screen", "brightness", 100), ("screen", "brightness", 20)]
