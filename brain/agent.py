"""The TARS brain, a LangGraph agent with tools.

Graph:  START -> llm -> (tool calls? -> tools -> llm ...) -> END
Speed:  - answers can be streamed token by token (on_token) so speech starts early
        - "direct" tools (open app, play video...) end the turn right after the tool
          runs and the tool's own message is spoken, saving one LLM round trip
Usage:  answer, tools_used = Brain().run("open vs code")
"""
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from brain.prompts import SYSTEM_PROMPT
from tools import DIRECT_TOOLS, TOOLS

load_dotenv()

# Override with OPENAI_MODEL in .env. Pick a fast, cheap, tool-calling model.
DEFAULT_MODEL = "gpt-4.1-mini"


def _text(message) -> str:
    """Message content can be a string or a list of parts; return plain text."""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = [p.get("text", "") for p in content if isinstance(p, dict)]
    return " ".join(parts).strip()


def _final_text(messages) -> str:
    """The spoken answer: the last AI message, or the direct tool results."""
    last = messages[-1]
    if last.type != "tool":
        return _text(last)
    parts = []
    for m in reversed(messages):
        if m.type != "tool":
            break
        parts.append(_text(m))
    return " ".join(reversed(parts))


class Brain:
    def __init__(
        self,
        model=None,
        humor=30,               # 0-100, injected into the system prompt
        max_history=20,         # messages the model sees (about 5-10 turns)
        max_steps=10,           # graph steps per command; stops tool loops
        tools=None,
        reasoning_effort=None,  # e.g. "low" or "minimal" for faster replies (model dependent)
        llm=None,               # inject a model (used by tests)
    ):
        self.humor = humor
        self.max_history = max_history
        self.max_steps = max_steps
        self.tools = tools or TOOLS
        self.direct_tools = DIRECT_TOOLS
        self.streamed = False   # True if the last run() delivered text through on_token

        if llm is None:
            kwargs = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
            llm = ChatOpenAI(
                model=model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
                timeout=20,
                max_retries=1,
                **kwargs,
            )
        self._raw_llm = llm
        self.llm = llm.bind_tools(self.tools)
        self.graph = self._build_graph()
        self.reset()

    # ---------- graph ----------
    def _build_graph(self):
        def call_model(state: MessagesState):
            history = trim_messages(
                state["messages"],
                strategy="last",
                token_counter=len,          # count messages, not tokens
                max_tokens=self.max_history,
                start_on="human",           # never start mid tool-call
                include_system=False,
            )
            system = SystemMessage(
                SYSTEM_PROMPT.format(
                    now=datetime.now().strftime("%A, %d %B %Y, %I:%M %p"),
                    humor=self.humor,
                )
            )
            return {"messages": [self.llm.invoke([system] + history)]}

        graph = StateGraph(MessagesState)
        graph.add_node("llm", call_model)
        graph.add_node("tools", ToolNode(self.tools))
        graph.add_edge(START, "llm")
        graph.add_conditional_edges("llm", tools_condition)  # -> "tools" or END
        graph.add_conditional_edges("tools", self._after_tools, ["llm", END])
        return graph.compile(checkpointer=MemorySaver())

    def _after_tools(self, state: MessagesState):
        """End the turn if every tool that just ran is a 'direct' tool."""
        names = []
        for m in reversed(state["messages"]):
            if m.type != "tool":
                break
            names.append(m.name)
        if names and all(n in self.direct_tools for n in names):
            return END
        return "llm"

    # ---------- public ----------
    def reset(self):
        """Forget the conversation (new memory thread)."""
        self.thread_id = f"tars-{uuid.uuid4().hex[:8]}"

    def warm_up(self):
        """Open the network connection early so the first command is not slower."""
        try:
            self._raw_llm.invoke("Reply with OK.")
        except Exception as err:
            print(f"[brain] warm-up skipped: {err}")

    def run(self, text: str, on_token=None):
        """Process one command. Returns (spoken_answer, [tool names called]).

        If on_token is given, the final answer is streamed to it piece by piece
        (self.streamed tells whether that happened; otherwise speak the answer).
        """
        config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": self.max_steps,
        }
        self.streamed = False
        try:
            if on_token is None:
                state = self.graph.invoke({"messages": [HumanMessage(text)]}, config)
            else:
                state = self._run_streaming(text, config, on_token)
        except GraphRecursionError:
            self.reset()
            return "Sorry, I got stuck on that one.", []
        except Exception as err:
            print(f"[brain] error: {err}")
            self.reset()
            return "Sorry, I couldn't reach my brain just now.", []

        messages = state["messages"]
        last_human = max(i for i, m in enumerate(messages) if m.type == "human")
        tools_used = [
            call["name"]
            for m in messages[last_human + 1:]
            if m.type == "ai"
            for call in getattr(m, "tool_calls", [])
        ]
        return _final_text(messages), tools_used

    def _run_streaming(self, text, config, on_token):
        state = None
        tool_turn_ids = set()   # LLM messages that contain tool calls: never speak these
        for mode, payload in self.graph.stream(
            {"messages": [HumanMessage(text)]},
            config,
            stream_mode=["messages", "values"],
        ):
            if mode == "values":
                state = payload
                continue
            chunk, meta = payload
            if meta.get("langgraph_node") != "llm":
                continue
            if getattr(chunk, "tool_call_chunks", None):
                tool_turn_ids.add(chunk.id)
                continue
            if chunk.id in tool_turn_ids:
                continue
            token = _text(chunk) if not isinstance(chunk.content, str) else chunk.content
            if token:
                on_token(token)
                self.streamed = True
        return state