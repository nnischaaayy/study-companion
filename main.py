"""
Study Companion — Windows Desktop App Entry Point
"""
import threading
import time
import sys
import os
import socket
import uvicorn
import webview

from backend import create_app
from updater import check_for_update
from version import __version__

PORT = 8765
HOST = "127.0.0.1"

# Shared update state — written by background checker, read by /api/update-info
_update_info = {"available": False, "version": None, "url": None}


def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def is_already_running() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 47652))
        sock.listen(1)
        threading._single_instance_socket = sock
        return False
    except OSError:
        return True


def start_server(app):
    uvicorn.run(app, host=HOST, port=PORT, log_level="error")


def on_update_result(version, url):
    if version:
        _update_info["available"] = True
        _update_info["version"]   = version
        _update_info["url"]       = url


def main():
    if is_already_running():
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Study Companion is already running.\nCheck your taskbar.",
            "Study Companion",
            0x40,
        )
        sys.exit(0)

    os.environ["SC_WEB_DIR"]      = resource_path("web")
    os.environ["SC_VERSION"]      = __version__
    os.environ["SC_UPDATE_STATE"] = "checking"

    # Boot FastAPI — pass update_info dict so the route can read it
    app = create_app(update_info=_update_info)
    threading.Thread(target=start_server, args=(app,), daemon=True).start()

    # Check for updates silently in background (won't block startup)
    check_for_update(on_update_result)

    time.sleep(1.2)

    webview.create_window(
        title=f"Study Companion",
        url=f"http://{HOST}:{PORT}",
        width=1200,
        height=780,
        min_size=(960, 620),
        background_color="#1a1a1a",
        confirm_close=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
