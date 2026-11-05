"""Phase 7: open applications. Only apps listed in config/apps.yaml are allowed."""
from typing import Literal

from langchain_core.tools import tool

from tools._launch import APPS, close_app_windows, launch_app

# The allowlist comes from config/apps.yaml, so the LLM can only pick these names.
AppName = Literal[tuple(APPS)]


@tool
def open_app(app: AppName) -> str:
    """Open an application on the PC. Use for commands like 'open VS Code',
    'launch Chrome' or 'start Notepad'. Call once per application. Do not use
    it to search the web; use search_in_browser for that."""
    label = APPS[app].get("label", app)
    if launch_app(app):
        return f"Opening {label}."
    return f"Could not find {label} on this PC."


@tool
def close_app(app: AppName, force: bool = False) -> str:
    """Close an application on the PC, for example 'close VS Code' or 'close
    Chrome'. A normal close lets the app ask to save unsaved work. Set
    force=True ONLY if the user says 'force close', 'kill' or the app is stuck.
    To close just the current tab, use close_tab instead."""
    label = APPS[app].get("label", app)
    status = close_app_windows(app, force)
    return {
        "closed": f"Closed {label}.",
        "not_running": f"{label} is not running.",
        "still_running": f"{label} is still open. It may be asking you to save your work.",
        "unsupported": f"I can't close {label}.",
    }[status]


# Never press Ctrl+W while a terminal is focused: it could close the window TARS runs in.
_PROTECTED_TITLES = ("powershell", "command prompt", "cmd.exe", "terminal", "tars", "python", "uv ")


def _foreground_title() -> str:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


@tool
def close_tab() -> str:
    """Close the current tab in the window the user is looking at (browser or
    editor), like pressing Ctrl+W. Use for 'close this tab' or 'close the
    tab'. To close a whole application use close_app."""
    try:
        title = _foreground_title().lower()
    except Exception:
        title = ""
    if any(word in title for word in _PROTECTED_TITLES):
        return "I won't close tabs in the window I'm running in. Click the tab you want closed first."
    try:
        import pyautogui

        pyautogui.hotkey("ctrl", "w")
    except Exception as err:
        print(f"[close_tab] failed: {err}")
        return "Could not close the tab."
    return "Closed the tab."