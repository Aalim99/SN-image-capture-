import numpy as np

from capture_session import next_attempt_dir, sanitize_sn, save_capture


def _frame(color=0):
    return np.full((60, 80, 3), color, dtype=np.uint8)


def test_sanitize_sn_removes_illegal_chars():
    assert sanitize_sn('AB<>:"/\\|?*CD') == "AB_________CD"


def test_sanitize_sn_empty_falls_back():
    assert sanitize_sn("   ") == "UNKNOWN_SN"


def test_sanitize_sn_strips_whitespace():
    assert sanitize_sn("  SN123  ") == "SN123"


def test_next_attempt_dir_increments(tmp_path):
    sn_root = tmp_path / "SN123"
    first, n1 = next_attempt_dir(sn_root)
    second, n2 = next_attempt_dir(sn_root)

    assert (n1, n2) == (1, 2)
    assert first.name == "attempt_1"
    assert second.name == "attempt_2"
    assert first.exists() and second.exists()


def test_save_capture_creates_expected_files(tmp_path):
    attempt_dir = save_capture(
        output_dir=str(tmp_path),
        sn="SN-001",
        top_frame=_frame(10),
        top_ts=1000.0,
        bottom_frame=_frame(20),
        bottom_ts=1000.02,
        cameras_info={"top": "index 0", "bottom": "index 1"},
        jpeg_quality=90,
        capture_delay=3.0,
    )

    assert (attempt_dir / "top.jpg").exists()
    assert (attempt_dir / "bottom.jpg").exists()

    log_text = (attempt_dir / "log.txt").read_text(encoding="utf-8")
    assert "Serial Number: SN-001" in log_text
    assert "Attempt: 1" in log_text
    assert "Top/Bottom Frame Timestamp Skew" in log_text


def test_save_capture_versions_repeat_scans(tmp_path):
    kwargs = dict(
        output_dir=str(tmp_path),
        sn="SN-DUP",
        top_frame=_frame(1),
        top_ts=1.0,
        bottom_frame=_frame(2),
        bottom_ts=1.0,
        cameras_info={"top": "t", "bottom": "b"},
    )
    first = save_capture(**kwargs)
    second = save_capture(**kwargs)

    assert first != second
    assert first.name == "attempt_1"
    assert second.name == "attempt_2"
    assert (first / "top.jpg").exists()
    assert (second / "top.jpg").exists()


def test_sn_with_illegal_chars_still_produces_valid_folder(tmp_path):
    attempt_dir = save_capture(
        output_dir=str(tmp_path),
        sn="SN/123:BAD",
        top_frame=_frame(),
        top_ts=None,
        bottom_frame=_frame(),
        bottom_ts=None,
        cameras_info={"top": "t", "bottom": "b"},
    )
    assert attempt_dir.parent.name == "SN_123_BAD"
    log_text = (attempt_dir / "log.txt").read_text(encoding="utf-8")
    assert "Serial Number: SN/123:BAD" in log_text
