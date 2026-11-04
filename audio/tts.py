"""Phase 5: text-to-speech.

Main voice : edge-tts (natural, needs internet)
Fallback   : pyttsx3 (offline, robotic)
Barge-in   : press the interrupt key while it speaks to stop immediately
"""
import asyncio
import os
import re
import tempfile
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
            completed = self._speak_edge(text)
            self.last_engine = "edge-tts"
            return completed
        except Exception as err:
            print(f"[tts] edge-tts failed ({err}). Using offline voice.")
            self._speak_offline(text)
            self.last_engine = "pyttsx3"
            return True

    # ---------- edge-tts ----------
    def _speak_edge(self, text: str) -> bool:
        import edge_tts
        import pygame

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.close()
        try:
            async def _generate():
                comm = edge_tts.Communicate(
                    text, self.voice, rate=self.rate, volume=self.volume
                )
                await comm.save(tmp.name)

            asyncio.run(_generate())

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(tmp.name)
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
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass

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