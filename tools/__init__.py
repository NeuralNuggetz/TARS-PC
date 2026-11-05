"""All tools the agent can call. Add new tools here."""
from tools.apps import close_app, close_tab, open_app
from tools.browser import open_website, search_in_browser
from tools.media import play_youtube
from tools.system import system_control
from tools.web_search import web_search

TOOLS = [
    open_app, close_app, close_tab, search_in_browser, open_website,
    play_youtube, system_control, web_search,
]

# Tools whose result is already a good spoken reply. After they run, the turn ends
# and the tool's message is spoken as is (saves one LLM round trip, about 1-2 s).
# web_search is NOT here: its raw results must go back to the LLM to be summarized.
DIRECT_TOOLS = {
    "open_app",
    "close_app",
    "close_tab",
    "search_in_browser",
    "open_website",
    "play_youtube",
    "system_control",
}