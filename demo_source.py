"""Fake cameras that render a synthetic PCB, for running the app with no
hardware attached (python main.py --demo).

Boards cycle through the frame with gaps in between, so the real detect ->
countdown -> capture -> board-removed flow can be exercised end to end.
"""
import time
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).resolve().parent / "assets"
DEMO_SERIALS = ["SN-DEMO-0001", "SN-DEMO-0002", "SN-DEMO-0003"]

BOARD_VISIBLE_SECONDS = 9.0
GAP_SECONDS = 3.0
CYCLE = BOARD_VISIBLE_SECONDS + GAP_SECONDS

_BOARD_GREEN = (52, 92, 40)
_SOLDER = (168, 178, 182)


def _render_board(width, height, side, seed):
    """Draw a fake PCB: green substrate, silkscreen border, components."""
    frame = np.full((height, width, 3), (28, 30, 34), dtype=np.uint8)

    margin_x, margin_y = int(width * 0.08), int(height * 0.08)
    cv2.rectangle(frame, (margin_x, margin_y), (width - margin_x, height - margin_y), _BOARD_GREEN, -1)
    cv2.rectangle(frame, (margin_x, margin_y), (width - margin_x, height - margin_y), (86, 128, 74), 3)

    rng = np.random.default_rng(seed)
    for _ in range(26):
        x = int(rng.integers(margin_x + 20, width - margin_x - 70))
        y = int(rng.integers(margin_y + 20, height - margin_y - 50))
        w = int(rng.integers(18, 64))
        h = int(rng.integers(12, 40))
        shade = int(rng.integers(20, 70))
        cv2.rectangle(frame, (x, y), (x + w, y + h), (shade, shade, shade + 8), -1)
        cv2.rectangle(frame, (x, y), (x + w, y + h), _SOLDER, 1)

    for i in range(14):
        cx = margin_x + 30 + i * 26
        cv2.circle(frame, (cx, height - margin_y - 30), 5, _SOLDER, -1)

    cv2.putText(frame, f"{side.upper()} SIDE", (margin_x + 12, margin_y + 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 220, 200), 2)
    return frame


def _paste_qr(frame, qr_gray, top_left):
    qr_bgr = cv2.cvtColor(qr_gray, cv2.COLOR_GRAY2BGR)
    h, w = qr_bgr.shape[:2]
    x, y = top_left
    if y + h > frame.shape[0] or x + w > frame.shape[1]:
        return
    cv2.rectangle(frame, (x - 8, y - 8), (x + w + 8, y + h + 8), (255, 255, 255), -1)
    frame[y:y + h, x:x + w] = qr_bgr


class DemoCamera:
    def __init__(self, side: str, width: int = 1280, height: int = 720):
        self.side = side
        self.index = f"demo-{side}"
        self.width = width
        self.height = height
        self.actual_width = width
        self.actual_height = height
        self.connected = True
        self.error = None

        self._qr_images = {}
        for sn in DEMO_SERIALS:
            img = cv2.imread(str(ASSETS / f"{sn}.png"), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self._qr_images[sn] = cv2.resize(img, (190, 190), interpolation=cv2.INTER_NEAREST)

        self._boards = {
            sn: _render_board(width, height, side, seed=idx * 17 + (0 if side == "top" else 5))
            for idx, sn in enumerate(DEMO_SERIALS)
        }
        self._empty = np.full((height, width, 3), (24, 26, 30), dtype=np.uint8)
        cv2.putText(self._empty, "DEMO - no board in fixture", (int(width * 0.16), height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (90, 96, 110), 2)

        self._start = time.time()

    def _current_serial(self):
        elapsed = time.time() - self._start
        slot = int(elapsed // CYCLE)
        phase = elapsed % CYCLE
        if phase > BOARD_VISIBLE_SECONDS:
            return None
        return DEMO_SERIALS[slot % len(DEMO_SERIALS)]

    def latest(self):
        sn = self._current_serial()
        if sn is None:
            return self._empty.copy(), time.time()

        frame = self._boards[sn].copy()
        if self.side == "top" and sn in self._qr_images:
            _paste_qr(frame, self._qr_images[sn], (int(self.width * 0.62), int(self.height * 0.24)))
        return frame, time.time()

    def describe(self) -> str:
        return f"demo {self.side} camera, {self.width}x{self.height}"

    def open(self) -> bool:
        return True

    def reconfigure(self, index, width, height) -> bool:
        return True

    def close(self):
        pass


class DemoCameraManager:
    def __init__(self, width: int = 1280, height: int = 720):
        self.top = DemoCamera("top", width, height)
        self.bottom = DemoCamera("bottom", width, height)
        self.demo = True

    def open_all(self) -> bool:
        return True

    def reconfigure(self, top_index, bottom_index, width, height) -> bool:
        return True

    @property
    def both_connected(self) -> bool:
        return True

    def capture_pair(self):
        return self.top.latest(), self.bottom.latest()

    def close_all(self):
        pass
