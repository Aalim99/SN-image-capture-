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

### 1. Identify your camera indices

Run:

```
python list_cameras.py
```

This opens a preview window starting at camera index 0. Press **N** to
step to the next index, note which physical camera (top or bottom) shows
up at which index, then **Q** to quit.

### 2. Configure settings

Open Settings from within the app, or edit `settings.json` directly:

| Setting | Meaning |
|---|---|
| `output_dir` | Base folder where SN subfolders are created |
| `top_camera_index` / `bottom_camera_index` | From step 1 above |
| `camera_width` / `camera_height` | Capture resolution |
| `capture_delay_seconds` | Countdown after a barcode is decoded, before the shot is taken — gives you time to finish positioning the board |
| `barcode_lost_reset_seconds` | How long the barcode must be out of view before the *same* SN is allowed to trigger another capture |
| `jpeg_quality` | 1-100 |
| `barcode_stable_reads` | Consecutive identical reads required before a scan is accepted (guards against misreads) |

Changes to camera index/resolution require restarting the app.

### 3. Run it

```
python main.py
```

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
   captured, it will **not** keep re-triggering new attempts; only a
   genuine re-presentation (barcode out of view, then back) counts as a
   new attempt.
5. If a label is damaged or unreadable, type the SN into the **Manual SN**
   field and click **Capture Now** as a fallback — it goes through the
   same save/versioning logic.

`log.txt` records the serial number, attempt number, timestamp, image
filenames, camera indices/resolution, and the timestamp skew between the
two shots (see note below).

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
barcode decode/debounce logic) live in `tests/`:

```
pip install -r requirements-dev.txt
pytest
```

Camera capture itself isn't covered by these tests since it needs real
hardware — verify that on the actual Windows machine with both cameras
connected.
