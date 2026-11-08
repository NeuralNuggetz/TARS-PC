"""Show text in the on-screen TARS panel (see ui/overlay.py)."""
from langchain_core.tools import tool

_display = None   # set by main.py when the GUI is running


def set_display(callback):
    """callback(title, text) shows the panel; None means the GUI is off."""
    global _display
    _display = callback


@tool
def show_on_screen(title: str, text: str) -> str:
    """Show text on the screen in a small TARS panel. Use whenever the user says
    'show on screen', 'show it', 'display it' or 'put it on the screen'. For
    fresh information (news, scores) call web_search first, then this. title:
    2 to 5 words. text: plain text only, short lines, no markdown; start each
    list item with '- '. Keep it under about 120 words. The tool's reply is
    spoken for you, so do not add more text."""
    if _display is None:
        return "The screen panel is turned off."
    _display(title.strip(), text.strip())
    return "Showing it on screen."