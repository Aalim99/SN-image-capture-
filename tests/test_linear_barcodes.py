"""Linear (1D) barcode support.

A linear barcode needs roughly 2 pixels per narrow bar to decode, so unlike
a QR code it fails silently when the label is small in frame. These tests
pin down both halves: the formats decode, and a too-small one is still
*located* so the UI can tell the operator why nothing happened.
"""
import io

import barcode
import cv2
import numpy as np
import pytest
from barcode.writer import ImageWriter

from barcode_scanner import decode_barcodes, decode_detections, locate_unreadable_barcode

LINEAR_CASES = [
    ("code128", "SN-PCB-000123", "SN-PCB-000123"),
    ("code39", "SNPCB000123", "SNPCB000123J"),  # code39 appends a checksum char
    ("ean13", "590123412345", "5901234123457"),
    ("itf", "12345678", "12345678"),
]


def _render(kind, value, dpi=600):
    cls = barcode.get_barcode_class(kind)
    buf = io.BytesIO()
    cls(value, writer=ImageWriter()).write(
        buf, options={"module_height": 10.0, "quiet_zone": 4.0, "dpi": dpi}
    )
    buf.seek(0)
    from PIL import Image

    return np.array(Image.open(buf).convert("RGB"))[:, :, ::-1].copy()


def _place(bar, bar_width, frame_w=1920, frame_h=1080):
    height = int(bar.shape[0] * bar_width / bar.shape[1])
    resized = cv2.resize(bar, (bar_width, height), interpolation=cv2.INTER_AREA)
    frame = np.full((frame_h, frame_w, 3), 70, np.uint8)
    y, x = (frame_h - height) // 2, (frame_w - bar_width) // 2
    frame[y:y + height, x:x + bar_width] = resized
    return frame


@pytest.mark.parametrize("kind,value,expected", LINEAR_CASES)
def test_linear_formats_decode(kind, value, expected):
    assert decode_barcodes(_render(kind, value)) == [expected]


@pytest.mark.parametrize("kind,value,expected", LINEAR_CASES)
def test_linear_decodes_inside_a_camera_sized_frame(kind, value, expected):
    frame = _place(_render(kind, value), bar_width=700)
    assert decode_barcodes(frame) == [expected]


def test_linear_detection_reports_position():
    frame = _place(_render("code128", "SN-PCB-000123"), bar_width=700)
    det = decode_detections(frame)[0]
    left, top, width, height = det.rect
    assert width > height, "a 1D barcode should be wider than it is tall"
    assert 0 <= left and 0 <= top


def test_too_small_barcode_is_located_even_though_it_cannot_be_decoded():
    frame = _place(_render("code128", "SN-PCB-000123"), bar_width=240)
    assert decode_barcodes(frame) == [], "expected this to be too small to decode"
    assert locate_unreadable_barcode(frame) is not None, (
        "an unreadable barcode must still be located so the UI can explain it"
    )


def test_no_false_unreadable_warning_on_a_frame_without_a_barcode():
    blank = np.full((1080, 1920, 3), 70, np.uint8)
    assert locate_unreadable_barcode(blank) is None
