"""Entry point for the PCB image capture app.

Starts the UI even when no cameras are attached, so the app can be set up
(and its camera indices chosen) before the hardware is connected. Run with
--demo to drive the whole workflow with synthetic cameras.
"""
import argparse
import sys

INSTALL_HINT = (
    "Install the dependencies first, from this folder:\n\n"
    "    pip install -r requirements.txt"
)

ZBAR_HINT = (
    "The barcode library (pyzbar) is installed but its ZBar DLL will not load.\n\n"
    "On Windows this almost always means the Visual C++ Redistributable for\n"
    "Visual Studio 2013 is missing. Install both vcredist_x64.exe and\n"
    "vcredist_x86.exe from Microsoft, then run this app again."
)


def _fatal(title, message):
    print(f"\n{title}\n{'-' * len(title)}\n{message}\n", file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass
    sys.exit(1)


def _check_dependencies():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "Python is installed without tkinter, which this app's UI needs.\n"
            "Reinstall Python from python.org with the default options "
            "(tcl/tk is included there).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import cv2  # noqa: F401
    except ImportError:
        _fatal("OpenCV is not installed", f"Could not import cv2.\n\n{INSTALL_HINT}")

    try:
        import PIL  # noqa: F401
    except ImportError:
        _fatal("Pillow is not installed", f"Could not import PIL.\n\n{INSTALL_HINT}")

    try:
        import pyzbar.pyzbar  # noqa: F401
    except ImportError as exc:
        if "zbar" in str(exc).lower():
            _fatal("Barcode library will not load", ZBAR_HINT)
        _fatal("pyzbar is not installed", f"Could not import pyzbar.\n\n{INSTALL_HINT}")
    except OSError:
        _fatal("Barcode library will not load", ZBAR_HINT)


def main():
    parser = argparse.ArgumentParser(description="PCB top/bottom image capture")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with synthetic cameras so the app works with no hardware attached",
    )
    args = parser.parse_args()

    _check_dependencies()

    import config as config_module
    from gui import App

    settings = config_module.load_settings()

    if args.demo:
        from demo_source import DemoCameraManager

        cam_mgr = DemoCameraManager()
        print("Demo mode: synthetic cameras, no hardware used.")
    else:
        import cv2

        from camera_manager import CameraManager

        try:
            # OpenCV prints alarming WARN lines for every empty camera index
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except AttributeError:
            pass

        cam_mgr = CameraManager(
            top_index=settings["top_camera_index"],
            bottom_index=settings["bottom_camera_index"],
            width=settings["camera_width"],
            height=settings["camera_height"],
        )
        cam_mgr.open_all()

        if not cam_mgr.both_connected:
            for cam in (cam_mgr.top, cam_mgr.bottom):
                if not cam.connected:
                    print(f"{cam.name} camera: {cam.error}", file=sys.stderr)
            print(
                "\nThe app will still open. To fix this:\n"
                "  - run 'python list_cameras.py' to see which indices exist\n"
                "  - set them in Settings, then press F5 to reconnect\n"
                "  - or run 'python main.py --demo' to try the app without cameras\n",
                file=sys.stderr,
            )

    app = App(cam_mgr, settings, demo=args.demo)
    app.mainloop()


if __name__ == "__main__":
    main()
