"""Operator console UI.

State machine (per tick):

  WATCHING   - scanning the top camera feed for a barcode. A newly-seen,
               not-already-captured SN starts a COUNTDOWN.
  COUNTDOWN  - configurable delay before the actual shot, so the operator
               has time to finish positioning the board. A different SN
               appearing mid-countdown restarts it for the new board.

After a successful save the captured SN is suppressed (won't retrigger)
until the barcode has been out of view for barcode_lost_reset_seconds -
that is what lets the same SN be re-captured later as a new attempt_N for
a genuine rework/retest, without spamming attempts while the board just
sits there already captured.
"""
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import cv2
from PIL import Image, ImageTk

import config as config_module
from barcode_scanner import BACKEND_NAME, StableBarcodeDetector, decode_detections
from capture_session import save_capture
from imaging import fit_letterbox

C = {
    "bg": "#0f1216",
    "panel": "#181d25",
    "panel_alt": "#1f2630",
    "border": "#2c3542",
    "video_bg": "#080a0d",
    "text": "#e8ecf3",
    "muted": "#8a94a6",
    "dim": "#5d6675",
    "accent": "#3b82f6",
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "err": "#ef4444",
}
FONT = "Segoe UI"
MONO = "Consolas"

TICK_MS = 25
DECODE_INTERVAL = 0.12   # seconds between barcode decodes (full-res decode is expensive)
PREVIEW_INTERVAL = 0.045  # ~22 fps preview refresh
HISTORY_LIMIT = 12

SETTINGS_FIELDS = [
    ("output_dir", "Output folder", str),
    ("top_camera_index", "Top camera index", int),
    ("bottom_camera_index", "Bottom camera index", int),
    ("camera_width", "Camera width", int),
    ("camera_height", "Camera height", int),
    ("capture_delay_seconds", "Capture delay (s)", float),
    ("barcode_lost_reset_seconds", "Barcode-lost reset (s)", float),
    ("jpeg_quality", "JPEG quality (1-100)", int),
    ("barcode_stable_reads", "Stable reads required", int),
]


def _button(parent, text, command, kind="normal"):
    colors = {
        "normal": (C["panel_alt"], C["text"]),
        "primary": (C["accent"], "#ffffff"),
        "ghost": (C["panel"], C["muted"]),
    }[kind]
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=colors[0],
        fg=colors[1],
        activebackground=C["border"],
        activeforeground=C["text"],
        relief="flat",
        borderwidth=0,
        padx=16,
        pady=8,
        font=(FONT, 10, "bold"),
        cursor="hand2",
    )


class CameraPane:
    """One video panel: title bar, live image, offline placeholder, overlays."""

    def __init__(self, parent, title, subtitle):
        self.container = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                                  highlightbackground=C["border"])

        header = tk.Frame(self.container, bg=C["panel"])
        header.pack(fill="x", padx=12, pady=(10, 8))

        tk.Label(header, text=title, bg=C["panel"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(header, text=subtitle, bg=C["panel"], fg=C["dim"],
                 font=(FONT, 9)).pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(header, text="connecting", bg=C["panel"],
                                     fg=C["muted"], font=(FONT, 9, "bold"))
        self.status_label.pack(side="right")

        self.canvas = tk.Canvas(self.container, bg=C["video_bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._photo = None

    def set_status(self, text, color):
        self.status_label.configure(text=text, fg=color)

    def show_offline(self, title, detail):
        self.canvas.delete("all")
        self._photo = None
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return
        self.canvas.create_text(w // 2, h // 2 - 14, text=title, fill=C["err"],
                                font=(FONT, 15, "bold"))
        self.canvas.create_text(w // 2, h // 2 + 14, text=detail, fill=C["dim"],
                                font=(FONT, 10), width=w - 40, justify="center")

    def show_frame(self, frame_bgr, detections=()):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        src_h, src_w = frame_bgr.shape[:2]
        draw_w, draw_h, off_x, off_y, scale = fit_letterbox(src_w, src_h, w, h)
        if draw_w <= 0:
            return

        resized = cv2.resize(frame_bgr, (draw_w, draw_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))

        self.canvas.delete("all")
        self.canvas.create_image(off_x, off_y, image=self._photo, anchor="nw")

        for det in detections:
            left, top, bw, bh = det.rect
            x1 = off_x + left * scale
            y1 = off_y + top * scale
            x2 = x1 + bw * scale
            y2 = y1 + bh * scale
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=C["ok"], width=3)
            self.canvas.create_text(x1, max(y1 - 12, 10), text=det.text, anchor="w",
                                    fill=C["ok"], font=(MONO, 11, "bold"))


class App(tk.Tk):
    def __init__(self, camera_manager, settings, demo=False):
        super().__init__()
        self.title("PCB Image Capture")
        self.geometry("1360x860")
        self.minsize(1050, 700)
        self.configure(bg=C["bg"])

        self.cam_mgr = camera_manager
        self.settings = settings
        self.demo = demo

        self.detector = StableBarcodeDetector(required_matches=settings["barcode_stable_reads"])
        self.state = "WATCHING"
        self.current_sn = None
        self.countdown_end = None
        self.last_captured_sn = None
        self.last_seen_time = None
        self.session_count = 0
        self.history = []
        self.flash_until = 0.0
        self.flash_text = None
        self.paused = False
        self._last_decode = 0.0
        self._last_preview = 0.0
        self._detections = []

        self._build_ui()
        self._tick()

    # ---------- layout ----------

    def _build_ui(self):
        self._build_header()

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        video_area = tk.Frame(body, bg=C["bg"])
        video_area.pack(side="left", fill="both", expand=True)

        self.top_pane = CameraPane(video_area, "TOP CAMERA", f"barcode read here · {BACKEND_NAME}")
        self.top_pane.container.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.bottom_pane = CameraPane(video_area, "BOTTOM CAMERA", "")
        self.bottom_pane.container.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self._build_sidebar(body)
        self._build_sn_panel()
        self._build_footer()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda _e: self._reconnect())

    def _build_header(self):
        header = tk.Frame(self, bg=C["bg"])
        header.pack(fill="x", padx=16, pady=(14, 10))

        title_box = tk.Frame(header, bg=C["bg"])
        title_box.pack(side="left")
        tk.Label(title_box, text="PCB IMAGE CAPTURE", bg=C["bg"], fg=C["text"],
                 font=(FONT, 16, "bold")).pack(anchor="w")
        mode = "DEMO MODE - synthetic cameras" if self.demo else "top + bottom capture, barcode linked"
        tk.Label(title_box, text=mode, bg=C["bg"],
                 fg=C["warn"] if self.demo else C["dim"], font=(FONT, 9)).pack(anchor="w")

        self.status_canvas = tk.Canvas(header, height=42, width=520, bg=C["bg"],
                                       highlightthickness=0)
        self.status_canvas.pack(side="right")

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=C["bg"], width=290)
        sidebar.pack(side="left", fill="y", padx=(12, 0))
        sidebar.pack_propagate(False)

        counter = tk.Frame(sidebar, bg=C["panel"], highlightthickness=1,
                           highlightbackground=C["border"])
        counter.pack(fill="x")
        tk.Label(counter, text="CAPTURED THIS SESSION", bg=C["panel"], fg=C["muted"],
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        self.count_label = tk.Label(counter, text="0", bg=C["panel"], fg=C["text"],
                                    font=(FONT, 34, "bold"))
        self.count_label.pack(anchor="w", padx=14, pady=(0, 10))

        hist = tk.Frame(sidebar, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["border"])
        hist.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(hist, text="RECENT CAPTURES", bg=C["panel"], fg=C["muted"],
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.history_frame = tk.Frame(hist, bg=C["panel"])
        self.history_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._render_history()

    def _build_sn_panel(self):
        panel = tk.Frame(self, bg=C["panel"], highlightthickness=1,
                         highlightbackground=C["border"])
        panel.pack(fill="x", padx=16, pady=(0, 8))

        left = tk.Frame(panel, bg=C["panel"])
        left.pack(side="left", fill="both", expand=True, padx=18, pady=14)
        tk.Label(left, text="SERIAL NUMBER", bg=C["panel"], fg=C["muted"],
                 font=(FONT, 9, "bold")).pack(anchor="w")
        self.sn_label = tk.Label(left, text="—", bg=C["panel"], fg=C["dim"],
                                 font=(MONO, 30, "bold"))
        self.sn_label.pack(anchor="w")

        right = tk.Frame(panel, bg=C["panel"])
        right.pack(side="right", padx=18, pady=14)
        self.countdown_label = tk.Label(right, text="", bg=C["panel"], fg=C["warn"],
                                        font=(FONT, 12, "bold"))
        self.countdown_label.pack(anchor="e")
        self.progress = tk.Canvas(right, width=340, height=12, bg=C["panel"],
                                  highlightthickness=0)
        self.progress.pack(anchor="e", pady=(8, 0))

    def _build_footer(self):
        footer = tk.Frame(self, bg=C["bg"])
        footer.pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(footer, text="Manual SN", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 10)).pack(side="left")
        self.manual_sn_var = tk.StringVar()
        entry = tk.Entry(footer, textvariable=self.manual_sn_var, width=26,
                         bg=C["panel_alt"], fg=C["text"], insertbackground=C["text"],
                         relief="flat", font=(MONO, 12))
        entry.pack(side="left", padx=(10, 8), ipady=6)
        entry.bind("<Return>", lambda _e: self._manual_capture())
        _button(footer, "Capture now", self._manual_capture, "primary").pack(side="left")

        _button(footer, "Settings", self._open_settings).pack(side="right")
        _button(footer, "Reconnect cameras  (F5)", self._reconnect).pack(side="right", padx=8)

        self.output_label = tk.Label(footer, text="", bg=C["bg"], fg=C["dim"], font=(FONT, 9))
        self.output_label.pack(side="right", padx=16)
        self._refresh_output_label()

    # ---------- drawing helpers ----------

    def _refresh_output_label(self):
        path = self.settings["output_dir"]
        if len(path) > 46:
            path = "…" + path[-45:]
        self.output_label.configure(text=f"saving to  {path}")

    def _draw_status(self, text, color, detail=""):
        canvas = self.status_canvas
        canvas.delete("all")
        w = int(canvas["width"])
        h = int(canvas["height"])
        canvas.create_rectangle(0, 0, w, h, fill=C["panel"], outline=C["border"])
        canvas.create_oval(16, h // 2 - 6, 28, h // 2 + 6, fill=color, outline=color)
        canvas.create_text(40, h // 2, text=text.upper(), anchor="w", fill=color,
                           font=(FONT, 11, "bold"))
        if detail:
            canvas.create_text(w - 14, h // 2, text=detail, anchor="e", fill=C["muted"],
                               font=(FONT, 10))

    def _draw_progress(self, fraction, color):
        canvas = self.progress
        canvas.delete("all")
        w = int(canvas["width"])
        h = int(canvas["height"])
        canvas.create_rectangle(0, 0, w, h, fill=C["panel_alt"], outline="")
        if fraction > 0:
            canvas.create_rectangle(0, 0, max(2, int(w * min(fraction, 1.0))), h,
                                    fill=color, outline="")

    def _render_history(self):
        for child in self.history_frame.winfo_children():
            child.destroy()

        if not self.history:
            tk.Label(self.history_frame, text="nothing captured yet", bg=C["panel"],
                     fg=C["dim"], font=(FONT, 9)).pack(anchor="w", padx=6, pady=6)
            return

        for stamp, sn, attempt in self.history[:HISTORY_LIMIT]:
            row = tk.Frame(self.history_frame, bg=C["panel_alt"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=stamp, bg=C["panel_alt"], fg=C["dim"],
                     font=(MONO, 9)).pack(side="left", padx=(8, 6), pady=5)
            tk.Label(row, text=sn, bg=C["panel_alt"], fg=C["text"],
                     font=(MONO, 10, "bold")).pack(side="left")
            tk.Label(row, text=f"#{attempt}", bg=C["panel_alt"], fg=C["ok"],
                     font=(FONT, 9, "bold")).pack(side="right", padx=8)

    # ---------- main loop ----------

    def _tick(self):
        now = time.time()
        top_frame, _ = self.cam_mgr.top.latest()
        bottom_frame, _ = self.cam_mgr.bottom.latest()

        if now - self._last_decode >= DECODE_INTERVAL and top_frame is not None:
            self._last_decode = now
            self._detections = decode_detections(top_frame)
            stable_sn = self.detector.update_from_texts([d.text for d in self._detections])
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

        if now - self._last_preview >= PREVIEW_INTERVAL:
            self._last_preview = now
            self._update_pane(self.top_pane, self.cam_mgr.top, top_frame, self._detections)
            self._update_pane(self.bottom_pane, self.cam_mgr.bottom, bottom_frame, ())

        self._run_state_machine(now, stable_sn)
        self.after(TICK_MS, self._tick)

    def _update_pane(self, pane, camera, frame, detections):
        if not camera.connected:
            pane.set_status("offline", C["err"])
            pane.show_offline("NO SIGNAL", camera.error or "camera not connected")
            return
        if frame is None:
            pane.set_status("starting", C["warn"])
            pane.show_offline("STARTING…", "waiting for the first frame")
            return
        pane.set_status("live", C["ok"])
        pane.show_frame(frame, detections)

    def _run_state_machine(self, now, stable_sn):
        if self.paused:
            self.state = "WATCHING"
            self.countdown_label.configure(text="")
            self._draw_progress(0, C["warn"])
            self._draw_status("paused", C["muted"], "settings are open")
            return

        blocked = self._capture_blocked_reason()

        if self.state == "COUNTDOWN":
            if stable_sn and stable_sn != self.current_sn and stable_sn != self.last_captured_sn:
                self._start_countdown(stable_sn)

            remaining = self.countdown_end - now
            if remaining <= 0:
                self._do_capture()
                return

            fraction = 1 - (remaining / max(self.settings["capture_delay_seconds"], 0.001))
            self.sn_label.configure(text=self.current_sn, fg=C["text"])
            self.countdown_label.configure(text=f"capturing in {remaining:.1f}s")
            self._draw_progress(fraction, C["warn"])
            self._draw_status("board detected", C["warn"], self.current_sn)
            return

        # WATCHING
        if stable_sn and not blocked and stable_sn != self.last_captured_sn:
            self._start_countdown(stable_sn)
            return

        self.countdown_label.configure(text="")
        self._draw_progress(0, C["warn"])

        if now < self.flash_until:
            self._draw_status("saved", C["ok"], self.flash_text)
            return

        if blocked:
            self.sn_label.configure(text="—", fg=C["dim"])
            self._draw_status("cameras not ready", C["err"], blocked)
        elif stable_sn:
            self.sn_label.configure(text=stable_sn, fg=C["muted"])
            self._draw_status("already captured", C["accent"], "remove board to capture again")
        else:
            self.sn_label.configure(text="—", fg=C["dim"])
            self._draw_status("watching for barcode", C["accent"],
                              "present a board to the top camera")

    # ---------- capture ----------

    def _capture_blocked_reason(self):
        if not self.cam_mgr.top.connected:
            return "top camera offline"
        if not self.cam_mgr.bottom.connected:
            return "bottom camera offline"
        if self.cam_mgr.top.latest()[0] is None or self.cam_mgr.bottom.latest()[0] is None:
            return "waiting for camera frames"
        return None

    def _start_countdown(self, sn):
        self.state = "COUNTDOWN"
        self.current_sn = sn
        self.countdown_end = time.time() + self.settings["capture_delay_seconds"]
        self.flash_until = 0.0

    def _manual_capture(self):
        sn = self.manual_sn_var.get().strip()
        if not sn:
            messagebox.showwarning("Manual capture", "Enter a serial number first.")
            return
        blocked = self._capture_blocked_reason()
        if blocked:
            messagebox.showerror("Capture failed", f"Cannot capture: {blocked}.")
            return
        self.current_sn = sn
        self._do_capture()
        self.manual_sn_var.set("")

    def _do_capture(self):
        (top_frame, top_ts), (bottom_frame, bottom_ts) = self.cam_mgr.capture_pair()
        if top_frame is None or bottom_frame is None:
            self.state = "WATCHING"
            self._draw_status("capture failed", C["err"], "no frame available")
            return

        cameras_info = {"top": self.cam_mgr.top.describe(), "bottom": self.cam_mgr.bottom.describe()}
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
            self.state = "WATCHING"
            self._draw_status("save failed", C["err"], str(exc))
            messagebox.showerror("Save failed", f"Could not write to the output folder:\n\n{exc}")
            return

        attempt = attempt_dir.name.replace("attempt_", "")
        self.last_captured_sn = self.current_sn
        self.last_seen_time = time.time()
        self.state = "WATCHING"
        self.session_count += 1
        self.count_label.configure(text=str(self.session_count))
        self.history.insert(0, (datetime.now().strftime("%H:%M:%S"), self.current_sn, attempt))
        del self.history[HISTORY_LIMIT:]
        self._render_history()

        self.sn_label.configure(text=self.current_sn, fg=C["ok"])
        self.flash_text = f"{self.current_sn}  attempt {attempt}"
        self.flash_until = time.time() + 2.5

    # ---------- actions ----------

    def _reconnect(self):
        self.cam_mgr.reconfigure(
            self.settings["top_camera_index"],
            self.settings["bottom_camera_index"],
            self.settings["camera_width"],
            self.settings["camera_height"],
        )

    def _open_settings(self):
        self.paused = True  # don't auto-capture while settings are half-edited
        SettingsDialog(self, self.settings, on_saved=self._settings_saved,
                       on_closed=self._settings_closed)

    def _settings_closed(self):
        self.paused = False
        self.detector = StableBarcodeDetector(required_matches=self.settings["barcode_stable_reads"])

    def _settings_saved(self, camera_changed):
        self._refresh_output_label()
        if camera_changed:
            self._reconnect()

    def _on_close(self):
        self.cam_mgr.close_all()
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings, on_saved, on_closed):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.on_closed = on_closed
        self._closed = False

        tk.Label(self, text="SETTINGS", bg=C["bg"], fg=C["text"],
                 font=(FONT, 13, "bold")).grid(row=0, column=0, columnspan=3,
                                               sticky="w", padx=18, pady=(16, 12))

        self.vars = {}
        for i, (key, label, _kind) in enumerate(SETTINGS_FIELDS, start=1):
            tk.Label(self, text=label, bg=C["bg"], fg=C["muted"],
                     font=(FONT, 10)).grid(row=i, column=0, sticky="w", padx=(18, 10), pady=5)
            var = tk.StringVar(value=str(settings.get(key, "")))
            self.vars[key] = var
            tk.Entry(self, textvariable=var, width=32, bg=C["panel_alt"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     font=(MONO, 10)).grid(row=i, column=1, pady=5, ipady=4)
            if key == "output_dir":
                _button(self, "Browse", lambda v=var: self._browse(v), "ghost").grid(
                    row=i, column=2, padx=(8, 18))

        tk.Label(self, text="Camera index / resolution changes reconnect the cameras immediately.",
                 bg=C["bg"], fg=C["dim"], font=(FONT, 9)).grid(
            row=len(SETTINGS_FIELDS) + 1, column=0, columnspan=3, sticky="w", padx=18, pady=(10, 0))

        buttons = tk.Frame(self, bg=C["bg"])
        buttons.grid(row=len(SETTINGS_FIELDS) + 2, column=0, columnspan=3, pady=16)
        _button(buttons, "Save", self._save, "primary").pack(side="left", padx=6)
        _button(buttons, "Cancel", self.destroy).pack(side="left", padx=6)

        self._center_on(parent)
        self.grab_set()

    def _center_on(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def destroy(self):
        if not self._closed:
            self._closed = True
            self.on_closed()
        super().destroy()

    def _browse(self, var):
        path = filedialog.askdirectory(parent=self)
        if path:
            var.set(path)

    def _save(self):
        new_settings = dict(self.settings)
        try:
            for key, _label, kind in SETTINGS_FIELDS:
                raw = self.vars[key].get().strip()
                new_settings[key] = raw if kind is str else kind(raw)
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter valid numbers where expected.",
                                 parent=self)
            return

        if not new_settings["output_dir"]:
            messagebox.showerror("Invalid input", "Output folder cannot be empty.", parent=self)
            return
        if not 1 <= new_settings["jpeg_quality"] <= 100:
            messagebox.showerror("Invalid input", "JPEG quality must be between 1 and 100.",
                                 parent=self)
            return

        camera_changed = any(
            new_settings[k] != self.settings[k]
            for k in ("top_camera_index", "bottom_camera_index", "camera_width", "camera_height")
        )

        config_module.save_settings(new_settings)
        self.settings.update(new_settings)
        self.on_saved(camera_changed)
        self.destroy()
