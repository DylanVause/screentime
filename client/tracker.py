"""
ScreenTime Tracker — Windows client.

Polls the active window every second, records sessions whenever focus changes,
buffers them locally, and uploads to the server periodically.
"""

import sys
import time
import logging
import signal
from datetime import datetime
from pathlib import Path

try:
    import win32gui
    import win32process
    import psutil
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

from config import load_config
from local_storage import LocalStorage
from uploader import Uploader

LOG_FILE = Path(__file__).parent / "tracker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# Windows that indicate the screen is idle/locked — don't record these.
IDLE_TITLES = {"", "Windows Default Lock Screen", "Lock Screen"}


def get_active_window() -> tuple[str | None, str | None]:
    """Return (app_name, window_title) for the currently focused window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            app = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            app = "unknown"
        return app, title
    except Exception as exc:
        log.debug("get_active_window: %s", exc)
        return None, None


def run() -> None:
    config = load_config()
    storage = LocalStorage(config)
    uploader = Uploader(config)

    poll_interval: float = config["tracking"]["poll_interval"]
    upload_interval: float = config["tracking"]["upload_interval"]
    min_session_seconds: int = config["tracking"].get("min_session_seconds", 2)

    current_app: str | None = None
    current_title: str | None = None
    session_start: datetime | None = None
    last_upload = time.monotonic()

    device_name = config["device"]["name"]
    server_url = config["server"]["url"]

    log.info("Tracker started. Device: %s  Server: %s", device_name, server_url)

    # Graceful shutdown
    running = True

    def _stop(sig, frame):
        nonlocal running
        log.info("Shutting down…")
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        app, title = get_active_window()
        now = datetime.utcnow()

        # Treat completely empty/idle windows as None so we don't record them.
        if title in IDLE_TITLES:
            app, title = None, None

        window_changed = (app != current_app) or (title != current_title)

        if window_changed:
            # Close out previous session.
            if current_app and session_start:
                duration = int((now - session_start).total_seconds())
                if duration >= min_session_seconds:
                    storage.save_session(
                        {
                            "start": session_start.isoformat(),
                            "end": now.isoformat(),
                            "app": current_app,
                            "title": current_title or "",
                            "duration_seconds": duration,
                        }
                    )
            current_app = app
            current_title = title
            session_start = now if app else None

        # Periodic upload.
        if time.monotonic() - last_upload >= upload_interval:
            _do_upload(storage, uploader)
            last_upload = time.monotonic()

        time.sleep(poll_interval)

    # Final upload on shutdown.
    if current_app and session_start:
        now = datetime.utcnow()
        duration = int((now - session_start).total_seconds())
        if duration >= min_session_seconds:
            storage.save_session(
                {
                    "start": session_start.isoformat(),
                    "end": now.isoformat(),
                    "app": current_app,
                    "title": current_title or "",
                    "duration_seconds": duration,
                }
            )
    _do_upload(storage, uploader)
    log.info("Tracker stopped.")


def _do_upload(storage: "LocalStorage", uploader: "Uploader") -> None:
    pending = storage.get_pending()
    if not pending:
        return
    ok, accepted = uploader.upload(pending)
    if ok:
        storage.mark_uploaded([s["id"] for s in pending])
        log.info("Uploaded %d sessions (%d accepted by server).", len(pending), accepted)
    else:
        log.warning("Upload failed — will retry next interval.")


if __name__ == "__main__":
    run()
