"""Tkinter UI: dual live preview, auto-capture state machine, settings dialog.

State machine (per tick, ~30x/sec):

  WATCHING   - scanning the top camera feed for a barcode. A newly-seen,
               not-already-captured SN starts a COUNTDOWN.
  COUNTDOWN  - configurable delay before the actual shot, so the operator
               has time to finish positioning the board. A different SN
               appearing mid-countdown restarts it for the new board.

After a successful save, the captured SN is "suppressed" (won't retrigger)
until the barcode has been out of view for barcode_lost_reset_seconds -
this is what lets the same SN be re-captured later as a new attempt_N for
a genuine rework/retest, while not spamming a new attempt on every tick
while the board just sits there already captured.
"""
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

import config as config_module
from barcode_scanner import StableBarcodeDetector
from capture_session import save_capture

SETTINGS_FIELDS = [
    ("output_dir", "Output Folder", str),
    ("top_camera_index", "Top Camera Index", int),
    ("bottom_camera_index", "Bottom Camera Index", int),
    ("camera_width", "Camera Width", int),
    ("camera_height", "Camera Height", int),
    ("capture_delay_seconds", "Capture Delay (s)", float),
    ("barcode_lost_reset_seconds", "Barcode-Lost Reset (s)", float),
    ("jpeg_quality", "JPEG Quality (1-100)", int),
]


class App(tk.Tk):
    def __init__(self, camera_manager, settings):
        super().__init__()
        self.title("PCB Image Capture")
        self.geometry("1280x760")
        self.minsize(900, 560)

        self.cam_mgr = camera_manager
        self.settings = settings

        self.detector = StableBarcodeDetector(required_matches=settings["barcode_stable_reads"])
        self.state = "WATCHING"
        self.current_sn = None
        self.countdown_end = None
        self.last_captured_sn = None
        self.last_seen_time = None
        self.status_override = None
        self.status_override_until = 0.0

        self._build_ui()
        self._tick()

    # ---------- UI construction ----------

    def _build_ui(self):
        video_frame = ttk.Frame(self)
        video_frame.pack(fill="both", expand=True, padx=8, pady=8)

        top_col = ttk.LabelFrame(video_frame, text="Top Camera (barcode read here)")
        top_col.pack(side="left", fill="both", expand=True, padx=4)
        self.top_label = ttk.Label(top_col)
        self.top_label.pack(fill="both", expand=True)

        bottom_col = ttk.LabelFrame(video_frame, text="Bottom Camera")
        bottom_col.pack(side="left", fill="both", expand=True, padx=4)
        self.bottom_label = ttk.Label(bottom_col)
        self.bottom_label.pack(fill="both", expand=True)

        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=8, pady=4)
        self.status_var = tk.StringVar(value="Watching for barcode...")
        ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 14)).pack(side="left")

        manual_frame = ttk.Frame(self)
        manual_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(manual_frame, text="Manual SN (if barcode unreadable):").pack(side="left")
        self.manual_sn_var = tk.StringVar()
        ttk.Entry(manual_frame, textvariable=self.manual_sn_var, width=30).pack(side="left", padx=4)
        ttk.Button(manual_frame, text="Capture Now", command=self._manual_capture).pack(side="left")
        ttk.Button(manual_frame, text="Settings", command=self._open_settings).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- main loop ----------

    def _tick(self):
        top_frame, _top_ts = self.cam_mgr.top.latest()
        bottom_frame, _bottom_ts = self.cam_mgr.bottom.latest()

        if top_frame is not None:
            self._render(self.top_label, top_frame)
        if bottom_frame is not None:
            self._render(self.bottom_label, bottom_frame)

        now = time.time()

        if top_frame is not None:
            stable_sn = self.detector.update(top_frame)
            if self.detector.raw_detected:
                self.last_seen_time = now
            elif (
                self.last_captured_sn is not None
                and self.last_seen_time is not None
                and now - self.last_seen_time >= self.settings["barcode_lost_reset_seconds"]
            ):
                self.last_captured_sn = None
        else:
            stable_sn = None

        if self.state == "WATCHING":
            if stable_sn and stable_sn != self.last_captured_sn:
                self._start_countdown(stable_sn)
            elif self.status_override is None or now >= self.status_override_until:
                self.status_var.set("Watching for barcode...")

        elif self.state == "COUNTDOWN":
            if stable_sn and stable_sn != self.current_sn and stable_sn != self.last_captured_sn:
                self._start_countdown(stable_sn)

            remaining = self.countdown_end - now
            if remaining <= 0:
                self._do_capture()
            else:
                self.status_var.set(f"SN {self.current_sn} detected — capturing in {remaining:.1f}s")

        if self.status_override is not None and now < self.status_override_until:
            self.status_var.set(self.status_override)
        elif self.status_override is not None:
            self.status_override = None

        self.after(33, self._tick)

    def _render(self, label, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        w = label.winfo_width() or 480
        h = label.winfo_height() or 360
        img = Image.fromarray(rgb).resize((max(w, 160), max(h, 120)))
        photo = ImageTk.PhotoImage(img)
        label.configure(image=photo)
        label.image = photo  # keep a reference so it isn't garbage-collected

    # ---------- capture flow ----------

    def _start_countdown(self, sn):
        self.state = "COUNTDOWN"
        self.current_sn = sn
        self.countdown_end = time.time() + self.settings["capture_delay_seconds"]
        self.status_override = None  # don't let a stale "Saved ..." message linger over the countdown

    def _manual_capture(self):
        sn = self.manual_sn_var.get().strip()
        if not sn:
            messagebox.showwarning("Manual Capture", "Enter a serial number first.")
            return
        self.current_sn = sn
        self._do_capture()

    def _do_capture(self):
        (top_frame, top_ts), (bottom_frame, bottom_ts) = self.cam_mgr.capture_pair()
        if top_frame is None or bottom_frame is None:
            messagebox.showerror("Capture Failed", "One or both cameras have no frame available.")
            self.state = "WATCHING"
            return

        cameras_info = {
            "top": f"index {self.cam_mgr.top.index}, {self.cam_mgr.top.width}x{self.cam_mgr.top.height}",
            "bottom": f"index {self.cam_mgr.bottom.index}, {self.cam_mgr.bottom.width}x{self.cam_mgr.bottom.height}",
        }
        try:
            attempt_dir = save_capture(
                output_dir=self.settings["output_dir"],
                sn=self.current_sn,
                top_frame=top_frame,
                top_ts=top_ts,
                bottom_frame=bottom_frame,
                bottom_ts=bottom_ts,
                cameras_info=cameras_info,
                jpeg_quality=self.settings["jpeg_quality"],
                capture_delay=self.settings["capture_delay_seconds"],
            )
        except OSError as exc:
            messagebox.showerror("Save Failed", str(exc))
            self.state = "WATCHING"
            return

        self.last_captured_sn = self.current_sn
        self.last_seen_time = time.time()
        self.state = "WATCHING"
        self.status_override = f"Saved {self.current_sn} → {attempt_dir}"
        self.status_override_until = time.time() + 2.5

    # ---------- settings / lifecycle ----------

    def _open_settings(self):
        SettingsDialog(self, self.settings)

    def _on_close(self):
        self.cam_mgr.close_all()
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.settings = settings

        self.vars = {}
        for row, (key, label, _kind) in enumerate(SETTINGS_FIELDS):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            var = tk.StringVar(value=str(settings.get(key, "")))
            self.vars[key] = var
            ttk.Entry(self, textvariable=var, width=32).grid(row=row, column=1, padx=6, pady=4)
            if key == "output_dir":
                ttk.Button(self, text="Browse", command=lambda v=var: self._browse(v)).grid(row=row, column=2, padx=4)

        note = ttk.Label(
            self,
            text="Camera index/resolution changes need an app restart to take effect.",
            foreground="#a06000",
        )
        note.grid(row=len(SETTINGS_FIELDS), column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=len(SETTINGS_FIELDS) + 1, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

    def _browse(self, var):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _save(self):
        new_settings = dict(self.settings)
        try:
            for key, _label, kind in SETTINGS_FIELDS:
                raw = self.vars[key].get().strip()
                new_settings[key] = kind(raw) if kind is not str else raw
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers where expected.")
            return

        if not new_settings["output_dir"]:
            messagebox.showerror("Invalid Input", "Output folder cannot be empty.")
            return

        config_module.save_settings(new_settings)
        self.settings.update(new_settings)
        messagebox.showinfo("Settings", "Saved. Restart the application for camera changes to take effect.")
        self.destroy()
