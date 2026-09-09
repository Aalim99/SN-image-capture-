import numpy as np
import qrcode

from barcode_scanner import StableBarcodeDetector, decode_barcodes


def _qr_frame(text, size=300):
    qr_img = qrcode.make(text).convert("RGB").resize((size, size))
    rgb = np.array(qr_img)
    return rgb[:, :, ::-1].copy()  # RGB -> BGR


def _blank_frame(size=300):
    return np.full((size, size, 3), 255, dtype=np.uint8)


def test_decode_barcodes_reads_qr_code():
    assert decode_barcodes(_qr_frame("SN-ABC-123")) == ["SN-ABC-123"]


def test_decode_barcodes_empty_on_blank_frame():
    assert decode_barcodes(_blank_frame()) == []


def test_stable_detector_requires_consecutive_matches():
    detector = StableBarcodeDetector(required_matches=2)
    frame = _qr_frame("SN-XYZ")

    assert detector.update(frame) is None  # 1st read: not yet stable
    assert detector.raw_detected is True
    assert detector.update(frame) == "SN-XYZ"  # 2nd consecutive read: stable


def test_stable_detector_resets_on_blank_frame():
    detector = StableBarcodeDetector(required_matches=2)
    frame = _qr_frame("SN-RESET")

    detector.update(frame)
    assert detector.update(frame) == "SN-RESET"

    blank = _blank_frame()
    assert detector.update(blank) is None
    assert detector.raw_detected is False

    # seeing the same SN again afterwards needs required_matches again
    assert detector.update(frame) is None
    assert detector.update(frame) == "SN-RESET"


def test_stable_detector_switches_to_new_value_after_required_matches():
    detector = StableBarcodeDetector(required_matches=2)
    frame_a = _qr_frame("SN-A")
    frame_b = _qr_frame("SN-B")

    detector.update(frame_a)
    assert detector.update(frame_a) == "SN-A"

    # a different code seen once resets the streak to 1, not yet stable
    assert detector.update(frame_b) is None
    assert detector.update(frame_b) == "SN-B"
