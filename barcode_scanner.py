"""Barcode/QR decoding from a live camera frame, with debounce.

The decoder backend is picked at import time, in preference order:

  zxing-cpp  broadest coverage (QR, DataMatrix, Code128, Code39, Aztec,
             PDF417, EAN/UPC...). Ships self-contained wheels, so it needs
             no extra system libraries - this is the one to have.
  pyzbar     ZBar. Good coverage but no DataMatrix, and on Windows its DLL
             needs the VC++ 2013 runtime installed, which often isn't.
  opencv     always present, but QR codes only.

Nothing here raises if a backend is missing: the app falls back and reports
which decoder is live, rather than refusing to start.
"""
from dataclasses import dataclass

import cv2

KNOWN_BACKENDS = ("zxing-cpp", "pyzbar", "opencv")


@dataclass(frozen=True)
class Detection:
    text: str
    rect: tuple  # (left, top, width, height) in frame pixels
    symbology: str


def _rect_from_points(points):
    xs = [int(p[0]) for p in points]
    ys = [int(p[1]) for p in points]
    left, top = min(xs), min(ys)
    return left, top, max(xs) - left, max(ys) - top


def _make_zxing(zxingcpp):
    def decode(frame_bgr):
        detections = []
        for result in zxingcpp.read_barcodes(frame_bgr):
            text = result.text.strip()
            if not text:
                continue
            pos = result.position
            corners = [
                (pos.top_left.x, pos.top_left.y),
                (pos.top_right.x, pos.top_right.y),
                (pos.bottom_right.x, pos.bottom_right.y),
                (pos.bottom_left.x, pos.bottom_left.y),
            ]
            detections.append(Detection(text, _rect_from_points(corners), str(result.format)))
        return detections

    return decode


def _make_pyzbar(zbar_decode):
    def decode(frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        detections = []
        for obj in zbar_decode(gray):
            try:
                text = obj.data.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
            if not text:
                continue
            r = obj.rect
            detections.append(Detection(text, (r.left, r.top, r.width, r.height), obj.type))
        return detections

    return decode


def _make_opencv():
    detector = cv2.QRCodeDetector()

    def decode(frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        try:
            ok, texts, points, _ = detector.detectAndDecodeMulti(gray)
        except cv2.error:
            return []
        if not ok or points is None:
            return []

        detections = []
        for text, quad in zip(texts, points):
            text = (text or "").strip()
            if text:
                detections.append(Detection(text, _rect_from_points(quad), "QRCODE"))
        return detections

    return decode


def _select_backend():
    try:
        import zxingcpp

        return "zxing-cpp", _make_zxing(zxingcpp)
    except ImportError:
        pass

    try:
        from pyzbar.pyzbar import decode as zbar_decode

        return "pyzbar", _make_pyzbar(zbar_decode)
    except (ImportError, OSError):
        # pyzbar raises at import time when its ZBar DLL cannot be loaded
        pass

    return "opencv", _make_opencv()


BACKEND_NAME, _decode = _select_backend()


def backend_description() -> str:
    if BACKEND_NAME == "zxing-cpp":
        return "zxing-cpp (QR, DataMatrix, Code128, Code39, EAN/UPC...)"
    if BACKEND_NAME == "pyzbar":
        return "pyzbar (QR, Code128, Code39, EAN/UPC - no DataMatrix)"
    return "OpenCV fallback (QR codes only - run 'pip install zxing-cpp' for more)"


def decode_detections(frame_bgr) -> list[Detection]:
    """Decode every readable code in the frame, keeping its position."""
    return _decode(frame_bgr)


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
