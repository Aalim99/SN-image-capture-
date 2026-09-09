"""Barcode/QR decoding from a live camera frame, with debounce.

Supports whatever ZBar supports (QR, Code128, Code39, EAN/UPC, PDF417, ...).
Does not support DataMatrix - if PCB labels use DataMatrix, swap in
pylibdmtx alongside this module.
"""
from dataclasses import dataclass

import cv2
from pyzbar.pyzbar import decode as zbar_decode


@dataclass(frozen=True)
class Detection:
    text: str
    rect: tuple  # (left, top, width, height) in frame pixels
    symbology: str


def decode_detections(frame_bgr) -> list[Detection]:
    """Decode every readable code in the frame, keeping its position."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    detections = []
    for obj in zbar_decode(gray):
        try:
            text = obj.data.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not text:
            continue
        rect = obj.rect
        detections.append(
            Detection(
                text=text,
                rect=(rect.left, rect.top, rect.width, rect.height),
                symbology=obj.type,
            )
        )
    return detections


def decode_barcodes(frame_bgr) -> list[str]:
    return [d.text for d in decode_detections(frame_bgr)]


class StableBarcodeDetector:
    """Only reports a value once it has read the same code N times in a row.

    Guards against a single misread frame triggering a capture under the
    wrong serial number.
    """

    def __init__(self, required_matches: int = 2):
        self.required_matches = max(1, required_matches)
        self._last_value = None
        self._count = 0
        self.raw_detected = False  # whether the most recent update saw any code at all

    def update(self, frame_bgr):
        return self.update_from_texts(decode_barcodes(frame_bgr))

    def update_from_texts(self, texts):
        """Feed already-decoded values, so the caller can decode just once."""
        value = texts[0] if texts else None
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
