"""Barcode/QR decoding from a live camera frame, with debounce.

Supports whatever ZBar supports (QR, Code128, Code39, EAN/UPC, PDF417, ...).
Does not support DataMatrix - if PCB labels use DataMatrix, swap in
pylibdmtx alongside this module.
"""
import cv2
from pyzbar.pyzbar import decode as zbar_decode


def decode_barcodes(frame_bgr) -> list[str]:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    results = []
    for obj in zbar_decode(gray):
        try:
            text = obj.data.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if text:
            results.append(text)
    return results


class StableBarcodeDetector:
    """Only reports a value once it has read the same code N times in a row.

    Guards against a single misread frame triggering a capture under the
    wrong serial number.
    """

    def __init__(self, required_matches: int = 2):
        self.required_matches = max(1, required_matches)
        self._last_value = None
        self._count = 0
        self.raw_detected = False  # whether the most recent update() saw any code at all

    def update(self, frame_bgr):
        codes = decode_barcodes(frame_bgr)
        value = codes[0] if codes else None
        self.raw_detected = value is not None

        if value is None:
            self._last_value = None
            self._count = 0
            return None

        if value == self._last_value:
            self._count += 1
        else:
            self._last_value = value
            self._count = 1

        return value if self._count >= self.required_matches else None
