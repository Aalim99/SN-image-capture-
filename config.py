"""Settings load/save for the PCB capture app, backed by settings.json."""
import json
from pathlib import Path

DEFAULT_SETTINGS = {
    "output_dir": "C:/PCB_Captures",
    "top_camera_index": 0,
    "bottom_camera_index": 1,
    "camera_width": 1920,
    "camera_height": 1080,
    "capture_delay_seconds": 3.0,
    "barcode_lost_reset_seconds": 1.5,
    "jpeg_quality": 95,
    "barcode_stable_reads": 2,
}

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"


def load_settings() -> dict:
    data = {}
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    merged = {**DEFAULT_SETTINGS, **data}
    save_settings(merged)
    return merged


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
