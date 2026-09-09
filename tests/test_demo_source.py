"""Demo mode must produce frames whose barcode actually decodes - otherwise
'python main.py --demo' silently never triggers a capture."""
import demo_source
from barcode_scanner import decode_barcodes
from demo_source import DEMO_SERIALS, DemoCameraManager


def _top_frame_for_serial(monkeypatch, serial):
    monkeypatch.setattr(demo_source.DemoCamera, "_current_serial", lambda self: serial)
    mgr = DemoCameraManager(width=1280, height=720)
    frame, _ts = mgr.top.latest()
    return frame


def test_demo_top_frame_barcode_decodes(monkeypatch):
    frame = _top_frame_for_serial(monkeypatch, DEMO_SERIALS[0])
    assert decode_barcodes(frame) == [DEMO_SERIALS[0]]


def test_every_demo_serial_decodes(monkeypatch):
    for serial in DEMO_SERIALS:
        frame = _top_frame_for_serial(monkeypatch, serial)
        assert decode_barcodes(frame) == [serial]


def test_bottom_frame_has_no_barcode(monkeypatch):
    monkeypatch.setattr(demo_source.DemoCamera, "_current_serial", lambda self: DEMO_SERIALS[0])
    mgr = DemoCameraManager(width=1280, height=720)
    frame, _ts = mgr.bottom.latest()
    assert decode_barcodes(frame) == []


def test_empty_fixture_frame_has_no_barcode(monkeypatch):
    frame = _top_frame_for_serial(monkeypatch, None)
    assert decode_barcodes(frame) == []
