"""Entry point for the PCB image capture app."""
import sys

import config as config_module
from camera_manager import CameraManager
from gui import App


def main():
    settings = config_module.load_settings()

    cam_mgr = CameraManager(
        top_index=settings["top_camera_index"],
        bottom_index=settings["bottom_camera_index"],
        width=settings["camera_width"],
        height=settings["camera_height"],
    )

    try:
        cam_mgr.open_all()
    except RuntimeError as exc:
        print(f"Camera error: {exc}", file=sys.stderr)
        print(
            "Run list_cameras.py to find the correct camera indices, "
            "then set them in Settings.",
            file=sys.stderr,
        )
        sys.exit(1)

    app = App(cam_mgr, settings)
    app.mainloop()


if __name__ == "__main__":
    main()
