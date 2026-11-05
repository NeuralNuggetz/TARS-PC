"""Phase 7: open the browser, show a search page, open well-known websites."""
import webbrowser
from typing import Literal
from urllib.parse import quote_plus

from langchain_core.tools import tool

from tools._launch import launch_app

SiteName = Literal["youtube", "github", "google", "gmail"]

SITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
}
LABELS = {"youtube": "YouTube", "github": "GitHub", "google": "Google", "gmail": "Gmail"}
SEARCH_URLS = {
    "google": "https://www.google.com/search?q=",
    "youtube": "https://www.youtube.com/results?search_query=",
}


def _open_url(url: str) -> bool:
    """Open in Chrome if installed, otherwise in the default browser."""
    if launch_app("chrome", [url]):
        return True
    return webbrowser.open(url)


@tool
def search_in_browser(query: str, site: Literal["google", "youtube"] = "google") -> str:
    """Open the browser (Chrome) and show a search page on Google (default) or
    YouTube. Use ONLY when the user asks to open the browser or to search/google
    something on screen, like 'search GitHub in the browser' or 'search lo-fi on
    YouTube'. It already opens the browser, so do not call open_app first. Do
    NOT use it to answer questions (use web_search) or to play a video
    (use play_youtube)."""
    url = SEARCH_URLS[site] + quote_plus(query)
    if _open_url(url):
        return f"Searching {LABELS[site]} for {query}."
    return "Could not open the browser."


@tool
def open_website(site: SiteName) -> str:
    """Open a well-known website in the browser, like YouTube or GitHub,
    without searching for anything."""
    if _open_url(SITES[site]):
        return f"Opening {LABELS[site]}."
    return "Could not open the browser."