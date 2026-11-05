"""Shared helpers: find and launch allowlisted apps defined in config/apps.yaml."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "apps.yaml"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows only


def _load_apps() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["apps"]


APPS = _load_apps()


def find_app(name: str):
    """Return the full path of an allowlisted app, or None if not installed."""
    for candidate in APPS.get(name, {}).get("paths", []):
        path = os.path.expandvars(candidate)
        if os.path.isfile(path):
            return path
        found = shutil.which(path)
        if found:
            return found
    return None


def launch_app(name: str, args=None) -> bool:
    """Start an allowlisted app (optionally with arguments). True if started."""
    exe = find_app(name)
    if not exe:
        return False
    try:
        subprocess.Popen([exe, *(args or [])], creationflags=_NO_WINDOW, close_fds=True)
        return True
    except OSError as err:
        print(f"[launch] failed to start {name}: {err}")
        return False


def _is_running(process: str) -> bool:
    """True if a process with this image name (for example Code.exe) is running."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=10,
        ).stdout
    except Exception:
        return False
    return process.lower() in out.lower()


def close_app_windows(name: str, force: bool = False) -> str:
    """Close an allowlisted app. Returns one of:
    closed, not_running, still_running, unsupported.

    Normal close asks the app to quit, so it can still ask you to save your work.
    force=True kills it immediately (unsaved work is lost).
    """
    cfg = APPS.get(name, {})

    if cfg.get("close") == "explorer":
        # Close folder windows only. Killing explorer.exe would remove the taskbar.
        script = "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, creationflags=_NO_WINDOW, timeout=15,
            )
        except Exception as err:
            print(f"[close] explorer failed: {err}")
            return "still_running"
        return "closed"

    process = cfg.get("process")
    if not process:
        return "unsupported"
    if not _is_running(process):
        return "not_running"

    cmd = ["taskkill", "/IM", process] + (["/F", "/T"] if force else [])
    try:
        subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW, timeout=15)
    except Exception as err:
        print(f"[close] taskkill failed: {err}")
        return "still_running"

    for _ in range(8):                      # wait up to 4 seconds
        time.sleep(0.5)
        if not _is_running(process):
            return "closed"
    return "still_running"