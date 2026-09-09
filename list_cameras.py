"""Setup helper: cycle through camera indices to see which physical camera
maps to which index, so you can set top_camera_index / bottom_camera_index
correctly in Settings.

Usage: python list_cameras.py
  N = try next camera index
  Q = quit
"""
import platform

import cv2


def _backend():
    return cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY


def main():
    index = 0
    cap = cv2.VideoCapture(index, _backend())
    print("Showing camera index 0. Press N for next index, Q to quit.")

    while True:
        if cap.isOpened():
            ok, frame = cap.read()
            if ok:
                cv2.putText(
                    frame,
                    f"Camera index: {index}  (N: next, Q: quit)",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("Identify cameras", frame)
        else:
            print(f"Index {index}: could not open")

        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), ord("Q")):
            break
        if key in (ord("n"), ord("N")):
            cap.release()
            index += 1
            cap = cv2.VideoCapture(index, _backend())
            print(f"Trying camera index {index}...")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
