"""Phase 7: volume, screenshot, time and date."""
from datetime import datetime
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

SystemAction = Literal[
    "volume_up", "volume_down", "mute", "screenshot", "time", "date"
]

VOLUME_PRESSES = 5   # each Windows volume key press is about 2%, so 5 = about 10%
SCREENSHOT_DIR = Path.home() / "Pictures" / "TARS_Screenshots"


def _press(key: str, times: int = 1):
    import pyautogui   # imported here so the module loads even if it is missing

    for _ in range(times):
        pyautogui.press(key)


def _screenshot() -> str:
    import pyautogui

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    pyautogui.screenshot().save(path)
    return "Screenshot saved in your Pictures folder."


@tool
def system_control(action: SystemAction) -> str:
    """Control the PC or read simple system info: volume up, volume down, mute,
    take a screenshot, tell the current time, or tell today's date."""
    if action == "time":
        return datetime.now().strftime("It is %I:%M %p.")
    if action == "date":
        return datetime.now().strftime("Today is %A, %B %d, %Y.")
    try:
        if action == "volume_up":
            _press("volumeup", VOLUME_PRESSES)
            return "Volume up."
        if action == "volume_down":
            _press("volumedown", VOLUME_PRESSES)
            return "Volume down."
        if action == "mute":
            _press("volumemute")
            return "Toggling mute."
        if action == "screenshot":
            return _screenshot()
    except Exception as err:
        print(f"[system] {action} failed: {err}")
        return f"Could not do {action}."
    return f"Unknown action {action}."