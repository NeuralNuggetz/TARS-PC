"""Play videos on YouTube.

yt-dlp finds the video (no API key needed), then Chrome opens it so it plays.
Install:  uv pip install yt-dlp     (keep it updated: uv pip install -U yt-dlp)
"""
import re
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from langchain_core.tools import tool

from tools._launch import launch_app
from tools.browser import SEARCH_URLS, _open_url

# Chrome blocks autoplay for pages opened without a click, so videos start paused.
# Videos are therefore opened in a separate TARS Chrome profile started with the
# autoplay switch. Sign in to YouTube once in that window and it is remembered.
# Set to False to use your normal Chrome (videos may open paused).
USE_AUTOPLAY_PROFILE = True
PROFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "chrome_profile"


def _play_url(url: str) -> bool:
    """Open a video so it starts playing on its own."""
    if USE_AUTOPLAY_PROFILE:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        flags = [
            "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if launch_app("chrome", flags + [url]):
            return True
    return _open_url(url)


_CHANNEL_CACHE = {}   # normalized query -> (channel_url, channel_name), this session only


def warm_up():
    """Import yt-dlp early (it takes a moment) so the first video lookup is faster."""
    try:
        import yt_dlp  # noqa: F401
    except Exception:
        pass


def _short(title: str, limit: int = 60) -> str:
    if len(title) <= limit:
        return title
    return title[:limit].rsplit(" ", 1)[0] + "..."


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _ydl_extract(url: str, count: int = 1) -> list:
    """Return up to `count` entries for a search or channel URL (metadata only)."""
    from yt_dlp import YoutubeDL

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": count,
        "socket_timeout": 10,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [e for e in (info.get("entries") or []) if e]


def _watch_url(entry: dict):
    video_id = entry.get("id")
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get("url")


def _pick_channel_entry(entries: list, query: str):
    """Prefer a result whose channel name matches the query (e.g. 'PewDiePie')."""
    q = _norm(query)
    for entry in entries:
        name = _norm(entry.get("channel") or entry.get("uploader"))
        if len(name) >= 3 and q and (q in name or name in q):
            return entry
    return entries[0] if entries else None


def _latest_from_channel(query: str):
    """Newest regular upload (not a Short) of the channel that matches the query."""
    key = _norm(query)
    ref = None
    if key in _CHANNEL_CACHE:
        channel_url, channel_name = _CHANNEL_CACHE[key]      # skips the search call
    else:
        ref = _pick_channel_entry(_ydl_extract(f"ytsearch5:{query}", 5), query)
        if not ref:
            return None
        channel_name = ref.get("channel") or ref.get("uploader")
        channel_url = ref.get("channel_url") or (
            f"https://www.youtube.com/channel/{ref['channel_id']}" if ref.get("channel_id") else None
        )
        if not channel_url:
            return ref   # cannot reach the channel page; use the search hit
        _CHANNEL_CACHE[key] = (channel_url, channel_name)
    videos = _ydl_extract(channel_url.rstrip("/") + "/videos", 1)
    entry = videos[0] if videos else (ref or {})
    if not _watch_url(entry):
        return ref
    entry.setdefault("channel", channel_name)
    return entry


def _best_match(query: str):
    entries = _ydl_extract(f"ytsearch1:{query}", 1)
    return entries[0] if entries else None


@tool
def play_youtube(query: str, which: Literal["best_match", "latest"] = "best_match") -> str:
    """Find a video on YouTube and start playing it in the browser. Use for
    'play X', 'play a song', or 'play the latest video from a channel'. The
    query is only the song, video title or channel name, without words like
    'play' or 'video'. Use which='latest' when the user asks for the recent,
    latest or newest video of a channel or creator; otherwise 'best_match'.
    Not for just showing search results; use search_in_browser for that."""
    try:
        entry = _latest_from_channel(query) if which == "latest" else _best_match(query)
    except Exception as err:
        print(f"[play_youtube] lookup failed: {err}")
        entry = None

    if not entry or not _watch_url(entry):
        _open_url(SEARCH_URLS["youtube"] + quote_plus(query))
        return "I couldn't pick a video, so I opened the YouTube search results instead."

    if not _play_url(_watch_url(entry)):
        return "Could not open the browser."
    title = _short(entry.get("title") or "the video")
    channel = entry.get("channel") or entry.get("uploader")
    return f"Playing {title}" + (f" from {channel}." if channel else ".")