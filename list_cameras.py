"""Setup helper: find which camera index is which physical camera.

    python list_cameras.py              scan indices and print what was found
    python list_cameras.py --preview 0  show a live window for one index (Q quits)

The scan always terminates on its own - it never sits in a loop waiting for
a camera that isn't there.
"""
import argparse
import platform
import sys

import cv2

MAX_INDEX = 9


def _backend():
    return cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY


def _quiet_opencv():
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except AttributeError:
        pass


def scan():
    found = []
    for index in range(MAX_INDEX + 1):
        cap = cv2.VideoCapture(index, _backend())
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                found.append((index, w, h))
        cap.release()

    if not found:
        print("No cameras found.")
        print("\nCheck that both cameras are plugged in and not in use by another")
        print("app (Teams, Zoom, Camera). To try the software without hardware:")
        print("    python main.py --demo")
        return found

    print(f"Found {len(found)} camera(s):\n")
    for index, w, h in found:
        print(f"  index {index}   {w}x{h}")
    print("\nPreview one to see which is physically top/bottom:")
    print(f"    python list_cameras.py --preview {found[0][0]}")
    print("\nThen set top_camera_index / bottom_camera_index in Settings.")
    return found


def preview(index):
    cap = cv2.VideoCapture(index, _backend())
    if not cap.isOpened():
        cap.release()
        print(f"Could not open camera index {index}. Run a plain scan first:")
        print("    python list_cameras.py")
        return 1

    print(f"Previewing camera index {index}. Press Q (or Esc) in the window to quit.")
    window = f"Camera index {index}"
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Lost the camera feed.")
            break

        cv2.putText(frame, f"index {index}  -  Q to quit", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow(window, frame)

        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Identify connected cameras")
    parser.add_argument("--preview", type=int, metavar="INDEX",
                        help="show a live window for one camera index")
    args = parser.parse_args()

    _quiet_opencv()
    if args.preview is not None:
        return preview(args.preview)
    scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
