"""Phase 8: live web search with Tavily.

Returns text for the LLM to summarize out loud. It does NOT open a browser;
that is search_in_browser's job.
Needs TAVILY_API_KEY in .env
"""
import os
from typing import Literal
from urllib.parse import urlparse

from langchain_core.tools import tool

MAX_RESULTS = 3
SNIPPET_CHARS = 250


@tool
def web_search(query: str, topic: Literal["general", "news"] = "general") -> str:
    """Search the web and return results that you summarize out loud. Use this
    for ANY question that needs current or recent information: latest news,
    recent events, scores, prices, or who currently holds a position. Use
    topic='news' for news questions. This does NOT open a browser. Do not use
    it for general knowledge you already know."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Web search is not set up because TAVILY_API_KEY is missing."

    try:
        from tavily import TavilyClient

        response = TavilyClient(api_key=api_key).search(
            query=query,
            topic=topic,
            max_results=MAX_RESULTS,
            include_answer=True,
        )
    except Exception as err:
        print(f"[web_search] error: {err}")
        return "Web search failed. Tell the user you could not reach the web."

    lines = []
    if response.get("answer"):
        lines.append(f"Summary: {response['answer']}")
    for item in response.get("results", [])[:MAX_RESULTS]:
        domain = urlparse(item.get("url", "")).netloc.removeprefix("www.")
        date = f" [{item['published_date']}]" if item.get("published_date") else ""
        content = (item.get("content") or "")[:SNIPPET_CHARS]
        lines.append(f"- {item.get('title', '')} ({domain}){date}: {content}")
    return "\n".join(lines) or "No results found."