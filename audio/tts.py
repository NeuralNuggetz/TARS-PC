"""Text-to-speech.

Main voice : edge-tts (natural, needs internet)
Fallback   : pyttsx3 (offline, robotic)
Barge-in   : press the interrupt key while it speaks to stop immediately
Streaming  : SpeechStream speaks sentence by sentence while the answer is still
             being generated (synthesis overlaps playback).
"""
import asyncio
import os
import queue
import re
import tempfile
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_EMOJI = re.compile(
    "[\U00010000-\U0010ffff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]", flags=re.UNICODE
)


def clean_text(text: str) -> str:
    """Make LLM output safe to read aloud: no markdown, URLs, code or emojis."""
    if not text:
        return ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)          # code blocks
    text = re.sub(r"`([^`]*)`", r"\1", text)                          # inline code
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)            # [text](url) -> text
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)                # bare URLs
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"^\s*[-*+•]\s+", "", text, flags=re.MULTILINE)     # bullets
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)    # numbered lists
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)          # quotes
    text = re.sub(r"[*_~|]+", "", text)                               # bold/italic/tables
    text = _EMOJI.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Words the voice mispronounces: regex pattern -> how it should be spoken.
# Only affects speech, not what is printed. Add your own entries here.
PRONUNCIATIONS = [
    (r"\bvs\s?code\b", "Visual Studio Code"),
    (r"\bvscode\b", "Visual Studio Code"),
]


def fix_pronunciation(text: str) -> str:
    for pattern, spoken in PRONUNCIATIONS:
        text = re.sub(pattern, spoken, text, flags=re.IGNORECASE)
    return text


def _remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


class Speaker:
    def __init__(
        self,
        voice="en-US-GuyNeural",   # list voices: edge-tts --list-voices
        rate="+0%",                # e.g. "+10%" faster, "-10%" slower
        volume="+0%",
        interrupt_key="f9",        # press while speaking to stop; None to disable
        max_chars=600,             # safety trim for very long answers
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.interrupt_key = interrupt_key
        self.max_chars = max_chars
        self.last_engine = None

    # ---------- public ----------
    def speak(self, text: str) -> bool:
        """Speak text and block until done. Returns False if interrupted."""
        text = fix_pronunciation(clean_text(text))[: self.max_chars]
        if not text:
            return True
        try:
            path = self._synth_to_file(text)
            try:
                completed = self._play_file(path)
            finally:
                _remove(path)
            self.last_engine = "edge-tts"
            return completed
        except Exception as err:
            print(f"[tts] edge-tts failed ({err}). Using offline voice.")
            self._speak_offline(text)
            self.last_engine = "pyttsx3"
            return True

    def begin_stream(self) -> "SpeechStream":
        """Start speaking text as it arrives. Call feed() then finish()."""
        return SpeechStream(self)

    # ---------- edge-tts ----------
    def _synth_to_file(self, text: str) -> str:
        """Generate speech and return the path of a temporary mp3 file."""
        import edge_tts

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.close()

        async def _generate():
            comm = edge_tts.Communicate(
                text, self.voice, rate=self.rate, volume=self.volume
            )
            await comm.save(tmp.name)

        try:
            asyncio.run(_generate())
        except Exception:
            _remove(tmp.name)
            raise
        return tmp.name

    def _play_file(self, path: str) -> bool:
        """Play an mp3. Returns False if the user pressed the interrupt key."""
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

        interrupted = False
        while pygame.mixer.music.get_busy():
            if self._interrupt_pressed():
                pygame.mixer.music.stop()
                interrupted = True
                break
            time.sleep(0.05)
        pygame.mixer.music.unload()   # release the file so Windows can delete it
        return not interrupted

    def _interrupt_pressed(self) -> bool:
        if not self.interrupt_key:
            return False
        try:
            import keyboard

            return keyboard.is_pressed(self.interrupt_key)
        except Exception:
            return False

    # ---------- offline fallback ----------
    def _speak_offline(self, text: str):
        import pyttsx3

        engine = pyttsx3.init()   # fresh engine each time avoids known hangs
        engine.say(text)
        engine.runAndWait()
        engine.stop()


class SpeechStream:
    """Speaks text sentence by sentence as it arrives.

    Two worker threads: one turns sentences into audio, the other plays them in
    order, so the next sentence is ready before the current one finishes.

        stream = speaker.begin_stream()
        stream.feed("Hello there. ")      # call as often as you like
        completed = stream.finish()       # blocks until everything has been spoken
    """

    _SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
    MIN_CHARS = 40   # shorter sentences are merged with the next one

    def __init__(self, speaker: Speaker):
        self.sp = speaker
        self.buffer = ""
        self.pending = ""
        self.sent_chars = 0
        self.first_audio_at = None        # time.time() when sound first started
        self.stop = threading.Event()
        self._text_q = queue.Queue()
        self._audio_q = queue.Queue()
        self._synth_thread = threading.Thread(target=self._synth_loop, daemon=True)
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._synth_thread.start()
        self._play_thread.start()

    @property
    def interrupted(self) -> bool:
        return self.stop.is_set()

    # ---------- producer side ----------
    def feed(self, text: str):
        if self.stop.is_set() or not text:
            return
        self.buffer += text
        *done, self.buffer = self._SPLIT.split(self.buffer)
        for sentence in done:
            self.pending = f"{self.pending} {sentence}".strip()
            if len(self.pending) >= self.MIN_CHARS:
                self._emit(self.pending)
                self.pending = ""

    def finish(self) -> bool:
        """Flush the rest, wait until speech ends. Returns False if interrupted."""
        if not self.stop.is_set():
            self._emit(f"{self.pending} {self.buffer}".strip())
        self.pending = self.buffer = ""
        self._text_q.put(None)
        self._play_thread.join()
        return not self.stop.is_set()

    def _emit(self, text: str):
        clean = fix_pronunciation(clean_text(text))
        if not clean or self.sent_chars + len(clean) > self.sp.max_chars:
            return
        self.sent_chars += len(clean)
        self._text_q.put(clean)

    # ---------- worker threads ----------
    def _synth_loop(self):
        try:
            while True:
                text = self._text_q.get()
                if text is None or self.stop.is_set():
                    break
                try:
                    self._audio_q.put(("file", self.sp._synth_to_file(text)))
                except Exception as err:
                    print(f"[tts] edge-tts failed ({err}). Using offline voice.")
                    self._audio_q.put(("offline", text))
        finally:
            self._audio_q.put(None)

    def _play_loop(self):
        try:
            while True:
                item = self._audio_q.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "file":
                    try:
                        if self.stop.is_set():
                            continue
                        if self.first_audio_at is None:
                            self.first_audio_at = time.time()
                        if not self.sp._play_file(payload):
                            self.stop.set()
                    finally:
                        _remove(payload)
                elif not self.stop.is_set():
                    if self.first_audio_at is None:
                        self.first_audio_at = time.time()
                    self.sp._speak_offline(payload)
        except Exception as err:
            print(f"[tts] playback error: {err}")
            self.stop.set()