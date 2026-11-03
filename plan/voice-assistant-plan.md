# Voice AI Assistant for Windows 11: Build Plan

## 1. Project Goal

A PC assistant you control by voice. It decides on its own whether a command is:

- **Task**: open VS Code, open Chrome and search "xyz", take a screenshot, change volume
- **Question**: "What is the recent news in AI?", "Explain transformers"

It replies by **voice** (and optionally on screen).

**Core flow:**
`Voice → Speech-to-Text → Agent (decides) → Tool OR Answer → Text-to-Speech → Voice`

---

## 2. Tech Stack

| Layer | Choice | Fallback |
|---|---|---|
| Language | Python 3.11 | - |
| Trigger | Hotkey (v1), Porcupine wake word (v2) | - |
| Audio input | `sounddevice` + VAD (`silero-vad` / `webrtcvad`) | `PyAudio` |
| Speech-to-text | `faster-whisper` (small/base) | Whisper API |
| Brain | LangGraph agent with tool calling | Plain LLM + JSON router |
| LLM | Claude or OpenAI API | Local model via Ollama |
| Web search | Tavily | SerpAPI / DuckDuckGo |
| Text-to-speech | `edge-tts` | `pyttsx3` (offline) |
| System control | `subprocess`, `os`, `webbrowser`, `pyautogui` | - |
| Config | `.env`, YAML | - |
| Logging | `logging` to file | - |

---

## 3. Folder Structure

```
voice-assistant/
├── main                 # entry point, runs the main loop
├── config/
│   ├── settings         # model names, hotkey, voice, thresholds
│   └── apps             # whitelist: app name -> Windows path/command
├── audio/
│   ├── recorder         # mic capture + silence detection
│   ├── stt              # speech-to-text
│   └── tts              # text-to-speech + playback
├── brain/
│   ├── agent            # LangGraph agent
│   ├── prompts          # system prompt, style rules
│   └── memory           # short conversation history
├── tools/
│   ├── apps             # open_app
│   ├── browser          # search in Chrome, open URL
│   ├── system           # volume, screenshot, lock, time, battery
│   ├── web_search       # live info for questions
│   └── files            # (later) open folder, find file
├── logs/
├── tests/
├── .env
└── requirements
```

---

## 4. Step-by-Step Plan

### Phase 1: Scope and Command List (Day 1)

**Goal:** Fix exactly what v1 will do.

Steps:
1. Write the v1 **task list** (start small):
   - Open apps: VS Code, Chrome, Notepad, Calculator, File Explorer
   - Chrome search for any query
   - Open a website (YouTube, GitHub)
   - Volume up/down/mute
   - Take a screenshot
   - Tell time/date
2. Write the v1 **question types**:
   - General knowledge
   - Current news / recent info (needs web search)
   - Coding questions (short spoken answers only)
3. Write 5 sample spoken phrases per command. These become your test set later.
4. Decide the trigger: **hotkey push-to-talk** for v1.
5. Decide the reply style: short (1 to 3 sentences) because it is spoken.

**Output:** A `commands` list document.

---

### Phase 2: Environment Setup (Day 1)

Steps:
1. Install Python 3.11 and create a virtual environment.
2. Create the folder structure above.
3. Get API keys: LLM provider, Tavily. Store them in `.env`.
4. Add `.env` to `.gitignore`.
5. Initialize git.
6. Check microphone and speakers work in Windows sound settings.
7. Check GPU availability (CUDA) for faster-whisper. CPU works too, just slower.

**Output:** Clean project skeleton, keys ready.

---

### Phase 3: Audio Input (Day 2)

**Goal:** Reliably capture your voice.

Steps:
1. List audio devices and pick the correct mic.
2. Record a fixed 5 seconds and save it. Play it back to verify quality.
3. Add **push-to-talk**: record while the hotkey is held, or start on hotkey and stop on silence.
4. Add **voice activity detection** so recording auto-stops after about 1 second of silence.
5. Add a max recording length (for example 15 seconds) as a safety stop.
6. Handle background noise: tune the VAD threshold.

**Test:** Say 10 phrases and check none are cut off at the start or end.

**Output:** A module that returns an audio buffer when you finish speaking.

---

### Phase 4: Speech-to-Text (Day 2)

Steps:
1. Install `faster-whisper` and load the `base` or `small` model.
2. Transcribe your saved recordings.
3. Measure **accuracy** and **latency** (target: under 2 seconds per command).
4. Set the language (English or Hinglish: test whether you need multilingual mode).
5. Add a **prompt hint** with your app names ("VS Code", "Chrome", "Statslane") so Whisper spells them correctly.
6. Filter empty or garbage transcripts (very short, silence hallucinations like "Thank you").

**Test:** 20 commands, record the word error rate informally.

**Output:** `audio → text` function.

---

### Phase 5: Text-to-Speech (Day 3)

Steps:
1. Install `edge-tts` and pick a voice (for example a natural en-IN or en-US voice).
2. Generate speech for a sample sentence and play it.
3. Add **playback control**: stop speaking immediately if the user presses the hotkey (barge-in).
4. Add `pyttsx3` as an offline fallback if there is no internet.
5. Add a **text cleaner** before speaking: remove markdown, URLs, emojis, code blocks.
6. Make sure the mic is **muted while speaking**, so the assistant does not hear itself.

**Test:** Pipe the STT output straight into TTS (echo test): you speak, it repeats.

**Output:** `text → voice` function. At this point you have **voice in and voice out**.

---

### Phase 6: The Brain, LangGraph Agent (Day 4 to 5)

**Goal:** One agent that decides between answering and using a tool.

Steps:
1. Write the **system prompt**:
   - You are a voice assistant on Windows 11
   - For actions, call a tool
   - For questions, answer directly; for current info, use web search
   - Keep answers short and speakable; no markdown
   - Ask a clarifying question if the command is ambiguous
2. Define tool schemas (name, description, arguments) for each tool. Clear descriptions matter most, because the LLM picks tools from them.
3. Build the LangGraph graph: `input → LLM → (tool call → tool result → LLM) → final answer`.
4. Add short **conversation memory** (last 5 to 10 turns) so follow-ups work ("open it again", "search that on YouTube").
5. Add a hard **iteration limit** to prevent tool loops.
6. Test the brain in **text mode** first (type instead of speak) to debug routing without audio noise.

**Test:** Run your 5-phrases-per-command list through text mode. Log which tool was picked and whether it was correct.

**Output:** `text → (action result or answer)` function.

---

### Phase 7: Task Tools (Day 5 to 6)

Build and test each tool **independently** before connecting to the agent.

**7.1 `open_app`**
- Whitelist file mapping friendly names and aliases ("vs code", "code", "visual studio code") to the real command or path.
- Verify the app exists; return a clear success or failure message.
- Never accept a raw path or command from the LLM, only a name from the whitelist.

**7.2 `search_in_browser`**
- Build a search URL from the query and open it in Chrome.
- Support other targets: YouTube search, Google Maps, GitHub.

**7.3 `open_website`**
- Map known sites by name; validate any URL (http/https only).

**7.4 `system_control`**
- Volume up/down/mute, screenshot, lock screen, current time, battery.
- Dangerous actions (shutdown, restart, delete) are either excluded in v1 or require spoken confirmation ("Say yes to confirm").

**7.5 Safety rules**
- Allowlist only. No arbitrary shell execution.
- Log every tool call with arguments and result.
- Return short, speakable results ("Opened VS Code").

**Output:** A tested toolbox.

---

### Phase 8: Question Answering with Live Info (Day 6)

Steps:
1. Build the `web_search` tool: query → top results → trimmed text snippets.
2. The agent uses it for anything time-sensitive (news, scores, prices, "latest", "today").
3. Instruct the LLM to **summarize** results in 2 to 3 spoken sentences and mention the source name, not the URL.
4. Add a rule: if the answer is general knowledge, do not search (saves time and cost).
5. Optionally let the user say "send me the links" to open the top results in the browser.

**Test:** "Recent news in AI", "Who won yesterday's match", "What is RAG": check that the first two search and the third does not.

**Output:** Reliable Q&A.

---

### Phase 9: Integration, Full Loop (Day 7)

Steps:
1. Build `main`: hotkey → record → transcribe → agent → speak.
2. Add states: idle, listening, thinking, speaking. Print or play a small sound for each so you know what it is doing.
3. Add error handling for:
   - No mic or mic busy
   - Empty transcript ("I didn't catch that")
   - API timeout or no internet (fall back to offline TTS and a spoken error)
   - Tool failure (speak what failed)
4. Add logging: transcript, chosen tool, result, latency per stage.
5. Measure **end-to-end latency** and note the slowest stage.

**Test:** 30 real spoken commands across tasks and questions.

**Output:** A working v1.

---

### Phase 10: Optimization (Day 8)

Steps:
1. Reduce latency:
   - Smaller or quantized Whisper model, GPU if available
   - Stream the LLM response and start TTS on the first sentence
   - Keep models loaded in memory (no reload per command)
2. Cache TTS for frequent phrases ("Opening VS Code").
3. Tune the VAD silence timeout (too long feels slow, too short cuts you off).
4. Consider a fast cheap model for routing and a stronger model only for complex answers.

**Target:** Task commands under 3 seconds, questions under 5 seconds to first spoken word.

---

### Phase 11: Polish and v2 Features (Day 9+)

Pick in this order:
1. **Wake word** (Porcupine): "Hey Jarvis" instead of the hotkey.
2. **System tray app** with a mute toggle and quit.
3. **Autostart** with Windows.
4. **Personalization**: your common apps, folders, and projects.
5. More tools: file search, open project folders, music control, reminders, calendar, email read-out, clipboard actions.
6. **Long-term memory**: remember preferences between sessions.
7. **Simple UI**: small overlay showing the transcript and the response.
8. **Multilingual** commands (English + Hindi).
9. **Screen-aware** commands (screenshot → vision model: "What's on my screen?").

---

## 5. Testing Strategy

- **Test set:** 5+ phrases per command, plus ambiguous and nonsense phrases.
- **Metrics:** transcript accuracy, correct tool chosen, correct arguments, task success, latency.
- **Conditions:** quiet room, fan or music noise, different distances from the mic.
- **Regression:** re-run the full set after every prompt or tool change.
- **Failure log:** keep a list of misrouted commands, then fix the prompt or tool descriptions.

---

## 6. Risks and Fixes

| Risk | Fix |
|---|---|
| Wrong command heard | Prompt hints for app names, confirmation for risky actions |
| LLM runs something dangerous | Strict allowlist, no shell access, confirmation step |
| Assistant hears itself | Mute mic during playback |
| Slow responses | Smaller models, streaming, GPU, keep models warm |
| Wrong tool picked | Clearer tool descriptions, fewer overlapping tools |
| No internet | Offline TTS fallback, spoken error, optional local LLM |
| Long answers read aloud | Strict short-answer rule plus a max-length trim |
| API key leaked | `.env`, `.gitignore`, never log keys |

---

## 7. Milestones Checklist

- [ ] M1: Scope and command list finalized
- [ ] M2: Environment and skeleton ready
- [ ] M3: Mic capture with silence detection works
- [ ] M4: Speech-to-text accurate and fast enough
- [ ] M5: Text-to-speech works, mic muted during playback
- [ ] M6: Agent routes correctly in text mode
- [ ] M7: All v1 task tools tested independently
- [ ] M8: Web-search Q&A works
- [ ] M9: Full voice loop working end to end
- [ ] M10: Latency targets met
- [ ] M11: Wake word, tray app, autostart

---

## 8. Immediate Next Step

Start with **Phase 1**: finalize the v1 command list and the exact app names, then move to Phases 3, 4 and 5 (voice in and voice out) before building the brain.
