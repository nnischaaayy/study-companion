# updater.py — Checks GitHub Releases API for a newer version
# Runs in a background thread on startup, never blocks the UI

import threading
import urllib.request
import urllib.error
import json
from version import __version__, GITHUB_OWNER, GITHUB_REPO


def _parse_version(tag: str) -> tuple:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) for comparison."""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update(callback):
    """
    Fetch the latest GitHub release in a background thread.
    Calls callback(latest_version, download_url) if an update is available.
    Calls callback(None, None) if already up to date or check fails.
    """
    def _check():
        try:
            api_url = (
                f"https://api.github.com/repos/"
                f"{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            )
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": f"StudyCompanion/{__version__}",
                    "Accept":     "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())

            latest_tag  = data.get("tag_name", "")
            latest_ver  = _parse_version(latest_tag)
            current_ver = _parse_version(__version__)

            if latest_ver > current_ver:
                # Find the .exe asset download URL
                assets      = data.get("assets", [])
                download_url = next(
                    (a["browser_download_url"] for a in assets
                     if a["name"].endswith(".exe")),
                    data.get("html_url", ""),   # fall back to release page
                )
                callback(latest_tag.lstrip("v"), download_url)
            else:
                callback(None, None)

        except Exception:
            callback(None, None)   # silently fail — never crash the app

    threading.Thread(target=_check, daemon=True).start()
