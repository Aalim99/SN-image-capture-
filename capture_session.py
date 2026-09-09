"""Saving a captured top/bottom image pair to disk under its SN folder.

Layout: {output_dir}/{SN}/attempt_{N}/{top.jpg, bottom.jpg, log.txt}

Every capture (including the first) gets an attempt_N folder so there is
no special-casing between a first-time scan and a rework re-scan of the
same SN - a re-scan just gets the next attempt number, and nothing already
on disk is ever overwritten.
"""
import re
from datetime import datetime
from pathlib import Path

import cv2

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_sn(raw_sn: str) -> str:
    """Make a decoded barcode value safe to use as a Windows folder name."""
    cleaned = _INVALID_CHARS.sub("_", raw_sn.strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "UNKNOWN_SN"


def next_attempt_dir(sn_root: Path) -> tuple[Path, int]:
    sn_root.mkdir(parents=True, exist_ok=True)
    existing_numbers = []
    for d in sn_root.iterdir():
        if d.is_dir() and d.name.startswith("attempt_"):
            suffix = d.name[len("attempt_"):]
            if suffix.isdigit():
                existing_numbers.append(int(suffix))
    n = max(existing_numbers, default=0) + 1
    attempt_dir = sn_root / f"attempt_{n}"
    attempt_dir.mkdir()
    return attempt_dir, n


def save_capture(
    output_dir: str,
    sn: str,
    top_frame,
    top_ts: float,
    bottom_frame,
    bottom_ts: float,
    cameras_info: dict,
    jpeg_quality: int = 95,
    capture_delay: float = 0.0,
) -> Path:
    clean_sn = sanitize_sn(sn)
    sn_root = Path(output_dir) / clean_sn
    attempt_dir, attempt_n = next_attempt_dir(sn_root)

    top_path = attempt_dir / "top.jpg"
    bottom_path = attempt_dir / "bottom.jpg"
    log_path = attempt_dir / "log.txt"

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
    cv2.imwrite(str(top_path), top_frame, encode_params)
    cv2.imwrite(str(bottom_path), bottom_frame, encode_params)

    skew_ms = abs((top_ts - bottom_ts) * 1000) if top_ts and bottom_ts else None
    lines = [
        f"Serial Number: {sn}",
        f"Sanitized Folder Name: {clean_sn}",
        f"Attempt: {attempt_n}",
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Capture Delay Setting: {capture_delay:.1f}s",
        f"Top Image: {top_path.name}",
        f"Bottom Image: {bottom_path.name}",
        f"Top Camera: {cameras_info.get('top')}",
        f"Bottom Camera: {cameras_info.get('bottom')}",
    ]
    if skew_ms is not None:
        lines.append(f"Top/Bottom Frame Timestamp Skew: {skew_ms:.1f} ms")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return attempt_dir
