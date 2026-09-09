"""Dual USB camera capture.

Each camera runs its own background thread continuously pulling frames as
fast as the device delivers them. This keeps the live preview smooth and
means "simultaneous" capture is just reading each camera's most recently
stored frame - for a static PCB sitting in a fixture, the two frames are
never more than one camera frame-interval apart (a few tens of ms), which
is indistinguishable from a true hardware-synced capture for this purpose.

Opening a camera never raises: a missing or busy device leaves the camera
in a disconnected state with an error message the UI can show, so the app
still starts with no hardware attached.
"""
import platform
import threading
import time

import cv2

MAX_READ_FAILURES = 60  # consecutive failed reads before declaring a disconnect


def _default_backend():
    return cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY


class Camera:
    def __init__(self, index: int, width: int, height: int, name: str):
        self.index = index
        self.width = width
        self.height = height
        self.name = name

        self.connected = False
        self.error = None
        self.actual_width = None
        self.actual_height = None

        self._cap = None
        self._frame = None
        self._timestamp = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def open(self) -> bool:
        """Try to open the device. Returns success; never raises."""
        self.close()
        try:
            cap = cv2.VideoCapture(self.index, _default_backend())
        except cv2.error as exc:
            self.connected = False
            self.error = str(exc)
            return False

        if not cap.isOpened():
            cap.release()
            self.connected = False
            self.error = f"No camera found at index {self.index}"
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._cap = cap
        self.connected = True
        self.error = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def reconfigure(self, index: int, width: int, height: int) -> bool:
        self.index = index
        self.width = width
        self.height = height
        return self.open()

    def _loop(self):
        failures = 0
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                failures = 0
                with self._lock:
                    self._frame = frame
                    self._timestamp = time.time()
                continue

            failures += 1
            if failures >= MAX_READ_FAILURES:
                self.connected = False
                self.error = "Camera stopped responding (unplugged?)"
                self._running = False
                break
            time.sleep(0.01)

    def latest(self):
        """Return (frame, timestamp) for the most recent frame, or (None, None)."""
        with self._lock:
            if self._frame is None:
                return None, None
            return self._frame.copy(), self._timestamp

    def describe(self) -> str:
        if not self.connected:
            return f"index {self.index} (not connected)"
        size = f"{self.actual_width}x{self.actual_height}" if self.actual_width else "unknown size"
        return f"index {self.index}, {size}"

    def close(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None
            self._timestamp = None
        self.connected = False


class CameraManager:
    def __init__(self, top_index: int, bottom_index: int, width: int, height: int):
        self.top = Camera(top_index, width, height, name="top")
        self.bottom = Camera(bottom_index, width, height, name="bottom")

    def open_all(self) -> bool:
        top_ok = self.top.open()
        bottom_ok = self.bottom.open()
        return top_ok and bottom_ok

    def reconfigure(self, top_index: int, bottom_index: int, width: int, height: int) -> bool:
        top_ok = self.top.reconfigure(top_index, width, height)
        bottom_ok = self.bottom.reconfigure(bottom_index, width, height)
        return top_ok and bottom_ok

    @property
    def both_connected(self) -> bool:
        return self.top.connected and self.bottom.connected

    def capture_pair(self):
        """Return ((top_frame, top_ts), (bottom_frame, bottom_ts))."""
        return self.top.latest(), self.bottom.latest()

    def close_all(self):
        self.top.close()
        self.bottom.close()
