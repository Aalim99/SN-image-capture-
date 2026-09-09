"""Dual USB camera capture.

Each camera runs its own background thread continuously pulling frames as
fast as the device delivers them. This keeps the live preview smooth and
means "simultaneous" capture is just reading each camera's most recently
stored frame — for a static PCB sitting in a fixture, the two frames are
never more than one camera frame-interval apart (a few tens of ms), which
is indistinguishable from a true hardware-synced capture for this purpose.

True frame-accurate hardware sync would require trigger-capable industrial
cameras wired to a shared trigger line; that's not needed here since the
board isn't moving between the two shots.
"""
import platform
import threading
import time

import cv2


def _default_backend():
    return cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY


class Camera:
    def __init__(self, index: int, width: int, height: int, name: str):
        self.index = index
        self.width = width
        self.height = height
        self.name = name

        self._cap = None
        self._frame = None
        self._timestamp = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def open(self):
        self._cap = cv2.VideoCapture(self.index, _default_backend())
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open {self.name} camera (index {self.index})")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame
                    self._timestamp = time.time()
            else:
                time.sleep(0.01)

    def latest(self):
        """Return (frame, timestamp) for the most recently grabbed frame, or (None, None)."""
        with self._lock:
            if self._frame is None:
                return None, None
            return self._frame.copy(), self._timestamp

    def close(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._cap is not None:
            self._cap.release()


class CameraManager:
    def __init__(self, top_index: int, bottom_index: int, width: int, height: int):
        self.top = Camera(top_index, width, height, name="top")
        self.bottom = Camera(bottom_index, width, height, name="bottom")

    def open_all(self):
        self.top.open()
        self.bottom.open()

    def capture_pair(self):
        """Return ((top_frame, top_ts), (bottom_frame, bottom_ts))."""
        return self.top.latest(), self.bottom.latest()

    def close_all(self):
        self.top.close()
        self.bottom.close()
