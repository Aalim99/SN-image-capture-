# PCB Image Capture

Captures a top and bottom photo of a PCB, links them to the board's serial
number (read from a barcode/QR code via the top camera), and saves both
images plus a log file into a folder named after that serial number.

## Requirements

- Windows, 64-bit Python 3.10+
- Two UVC-compatible USB cameras (plain plug-and-play webcams work; see
  hardware notes below)
- A barcode or QR label on the PCB, visible to the top camera

## Setup

```
pip install -r requirements.txt
```

`pyzbar`'s Windows wheel bundles the ZBar DLL, so no separate barcode
library install is needed.

### Try it without any hardware

```
python main.py --demo
```

Demo mode runs the whole workflow against synthetic cameras: fake boards
carrying real QR codes move in and out of the fixture, so you can see
detection, the countdown, capturing and the saved folder structure before
your cameras arrive.

### 1. Identify your camera indices

```
python list_cameras.py                 scan and list every camera found
python list_cameras.py --preview 0     open a live window for one index
```

The scan always finishes on its own. Use the preview to see which physical
camera (top or bottom) is at which index — press **Q** in the window to close it.

### 2. Configure settings

Click **Settings** in the app, or edit `settings.json` directly:

| Setting | Meaning |
|---|---|
| `output_dir` | Base folder where SN subfolders are created |
| `top_camera_index` / `bottom_camera_index` | From step 1 above |
| `camera_width` / `camera_height` | Capture resolution |
| `capture_delay_seconds` | Countdown after a barcode is decoded, before the shot is taken — gives you time to finish positioning the board |
| `barcode_lost_reset_seconds` | How long the barcode must be out of view before the *same* SN is allowed to trigger another capture |
| `jpeg_quality` | 1-100 |
| `barcode_stable_reads` | Consecutive identical reads required before a scan is accepted (guards against misreads) |

Camera changes take effect immediately — no restart. Press **F5** any time
to reconnect cameras (e.g. after plugging one in).

### 3. Run it

```
python main.py
```

or double-click `run.bat`, which keeps the console window open so you can
read any message instead of it flashing closed.

## The interface

- **Top / bottom camera panels** — live view of both cameras. A detected
  barcode is boxed in green with its decoded value, so the operator can
  see exactly what the software is reading. A missing camera shows
  **NO SIGNAL** with the reason instead of stopping the app.
- **Status pill** (top right) — the current state: watching, board
  detected, saved, paused, or cameras not ready.
- **Serial number panel** — the decoded SN in large text plus the countdown
  bar to the shot.
- **Sidebar** — how many boards this session, and a running list of recent
  captures with time, SN and attempt number.
- **Footer** — manual SN entry, reconnect, settings, and where files are
  being saved.

## How it works

1. The app continuously watches the **top** camera's feed for a barcode/QR.
2. Once the same value has been read `barcode_stable_reads` times in a row,
   it's accepted as the serial number and a countdown starts
   (`capture_delay_seconds`).
3. When the countdown ends, both cameras are captured and saved to:

   ```
   {output_dir}/{SN}/attempt_1/top.jpg
   {output_dir}/{SN}/attempt_1/bottom.jpg
   {output_dir}/{SN}/attempt_1/log.txt
   ```

4. If that board is removed and the *same* SN is scanned again later (e.g.
   a rework retest), nothing is overwritten — it's saved as `attempt_2`,
   then `attempt_3`, and so on. While the board just sits there after being
   captured it will **not** keep re-triggering; only a genuine
   re-presentation (barcode out of view, then back) counts as a new attempt.
5. If a label is damaged or unreadable, type the SN into the **Manual SN**
   field and click **Capture now** — same save/versioning logic.

`log.txt` records the serial number, attempt number, timestamp, image
filenames, camera indices/resolution, and the timestamp skew between the
two shots.

## Troubleshooting

**`No module named 'cv2'` (or `pyzbar`, `PIL`)** — dependencies aren't
installed. Run `pip install -r requirements.txt` in this folder.

**`Unable to find zbar shared library` / `libzbar-64.dll` not found** —
install the Microsoft Visual C++ Redistributable for Visual Studio 2013
(both x64 and x86), which the bundled ZBar DLL depends on.

**"No camera found at index 0"** — the app still opens and shows NO SIGNAL.
Run `python list_cameras.py` to see which indices actually exist, set them
in Settings, then press F5. Also check no other app (Teams, Zoom, Camera)
is holding the camera.

**The barcode never gets detected** — check the green detection box appears
over the label in the top panel. If not: improve lighting, avoid glare on
the label, and make sure the label is in focus (fixed/manual-focus lenses
must be set for your working distance).

**The console window closes instantly** — use `run.bat` instead of
double-clicking the `.py` file.

## Hardware notes

Any UVC-compliant USB camera works. For consistent, repeatable captures,
prefer **manual or fixed focus** over autofocus (autofocus hunts between
shots and gives inconsistent framing/sharpness), and buy two of the same
model so both feeds behave identically. 5-8MP is plenty for both image
quality and reliable barcode decoding.

"Simultaneous" capture here means: each camera runs its own continuous
capture thread, and a trigger reads each camera's most-recently-grabbed
frame. For a static board sitting in a fixture, the two frames are at most
one camera frame-interval apart (tens of milliseconds) — indistinguishable
from true hardware sync for this purpose. `log.txt`'s timestamp-skew line
lets you confirm this in practice. True frame-accurate hardware
synchronization would require trigger-capable industrial cameras wired to
a shared trigger line.

## Barcode formats

Decoding uses ZBar (via `pyzbar`), which covers QR codes and most 1D
formats (Code128, Code39, EAN/UPC, etc.) — the two most common formats on
PCB traceability labels. It does **not** decode DataMatrix; if your labels
use DataMatrix, `pylibdmtx` would need to be added alongside it.

## Tests

Hardware-free tests (SN sanitizing, attempt versioning, save/log output,
barcode decode/debounce, preview geometry, demo frames) live in `tests/`:

```
pip install -r requirements-dev.txt
pytest
```

Camera capture itself isn't covered by these tests since it needs real
hardware — verify that on the actual Windows machine with both cameras
connected.
