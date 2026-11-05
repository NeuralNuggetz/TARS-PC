"""TARS: voice assistant main loop.

Wake mode (default):
    say "Hey TARS" -> "Hi Cooper, how can I help you?" -> say your command
    or in one go:  "TARS, open VS Code"
    After a reply, TARS keeps listening for a few seconds, so follow-ups need no wake word.
Hotkey mode: press the hotkey and speak.

Run from the project root:  uv run python main.py
Say "goodbye" or press Ctrl+C to quit.
"""
import logging
import re
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent

DEFAULTS = {
    "activation": "wake",
    "wake_aliases": ["tars", "tarz", "tass", "tarse"],
    "user_name": "Cooper",
    "greeting": "Hi {name}, how can I help you?",
    "command_wait_seconds": 6,
    "followup_seconds": 5,
    "hotkey": "f9",
    "mic_device": None,
    "silence_ms": 900,
    "whisper_model": "base.en",
    "whisper_language": "en",
    "tts_voice": "en-US-GuyNeural",
    "tts_rate": "+0%",
    "humor": 30,
    "beep": True,
    "reasoning_effort": None,
}

# Handled locally so they are instant and never need the LLM.
EXIT_PHRASES = {"exit", "quit", "goodbye", "good bye", "stop listening", "go to sleep"}
RESET_PHRASES = {"reset", "forget that", "new conversation", "clear memory"}


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    path = ROOT / "config" / "settings.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            settings.update(yaml.safe_load(f) or {})
    return settings


def setup_logging() -> logging.Logger:
    (ROOT / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        ROOT / "logs" / "tars.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log = logging.getLogger("tars")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    return log


def beep(settings: dict):
    if not settings["beep"]:
        return
    try:
        import winsound

        winsound.Beep(900, 80)
    except Exception:
        pass


def build_wake_regex(aliases):
    """Matches 'Hey TARS, ...' / 'TARS, ...' at the START of a phrase only."""
    names = "|".join(re.escape(a) for a in aliases)
    return re.compile(
        rf"^\W*(?:(?:hey|hi|hello|ok|okay|yo)\W+)?(?:{names})(?:'s)?\b[\s,.:;!?\-]*(.*)$",
        re.IGNORECASE | re.DOTALL,
    )


def split_wake(text: str, regex):
    """Return (wake word heard?, the rest of the phrase)."""
    match = regex.match(text)
    if not match:
        return False, text.strip()
    return True, match.group(1).strip(" ,.:;!?-\n")


def local_command(text: str):
    """Return 'exit', 'reset' or None for commands TARS handles itself."""
    words = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if words.startswith("tars "):
        words = words[5:].strip()
    if words in EXIT_PHRASES:
        return "exit"
    if words in RESET_PHRASES:
        return "reset"
    return None


def main():
    settings = load_settings()
    log = setup_logging()

    # Heavy imports here so the module itself stays light.
    from audio.recorder import Recorder
    from audio.stt import Transcriber
    from audio.tts import Speaker
    from brain.agent import Brain

    print("Starting TARS...")
    hotkey = settings["hotkey"]
    mode = settings["activation"]
    wake = build_wake_regex(settings["wake_aliases"])
    greeting = settings["greeting"].format(name=settings["user_name"])

    rec = Recorder(device=settings["mic_device"], silence_ms=settings["silence_ms"])
    stt = Transcriber(
        model_size=settings["whisper_model"], language=settings["whisper_language"]
    )
    spk = Speaker(
        voice=settings["tts_voice"], rate=settings["tts_rate"], interrupt_key=hotkey
    )
    brain = Brain(humor=settings["humor"], reasoning_effort=settings["reasoning_effort"])

    def process(command: str):
        """Run one command. Returns (quit?, user cut TARS off?)."""
        cmd = local_command(command)
        if cmd == "exit":
            spk.speak("Goodbye.")
            return True, False
        if cmd == "reset":
            brain.reset()
            spk.speak("Memory cleared.")
            return False, False

        t0 = time.time()
        stream = spk.begin_stream()                     # speech starts as soon as the first sentence is ready
        answer, tools = brain.run(command, on_token=stream.feed)
        t_brain = time.time() - t0
        if not brain.streamed:
            stream.feed(answer)                         # direct tool results and error messages
        print(f"TARS : {answer}")
        completed = stream.finish()
        first_audio = (stream.first_audio_at - t0) if stream.first_audio_at else 0.0
        print(
            f"       [stt {stt.last_latency:.2f}s | brain {t_brain:.2f}s | "
            f"first audio {first_audio:.2f}s | tools {tools or '-'}]"
        )
        log.info(
            "command=%r tools=%s reply=%r stt=%.2fs brain=%.2fs first_audio=%.2fs",
            command, tools, answer, stt.last_latency, t_brain, first_audio,
        )
        return False, not completed

    def warm_up():
        brain.warm_up()
        try:
            from tools.media import warm_up as warm_media

            warm_media()
        except Exception:
            pass

    threading.Thread(target=warm_up, daemon=True).start()   # runs while TARS greets you

    spk.speak("TARS online.")
    if mode == "wake":
        print("Say 'Hey TARS' (or just 'TARS' followed by a command). Ctrl+C to quit.")
    window = None   # wake mode: seconds to listen without a wake word (None = asleep)
    cut_off = False # hotkey mode: user interrupted TARS, so listen right away

    while True:
        try:
            if mode == "wake":
                # ---- listen for an utterance ----
                timeout = float("inf") if window is None else window
                audio = rec.record_until_silence(timeout=timeout)
                if audio is None:
                    if window is not None:
                        print("(back to sleep)")
                    window = None
                    continue
                heard = stt.transcribe(audio)
                if not heard:
                    continue

                woke, rest = split_wake(heard, wake)
                if window is None and not woke:
                    continue                      # asleep: ignore speech without the wake word
                command = rest if woke else heard
                window = None
                print(f"You  : {heard}")

                # "Hey TARS" alone: greet, then wait for the command
                if woke and not command:
                    spk.speak(greeting)
                    audio = rec.record_until_silence(timeout=settings["command_wait_seconds"])
                    command = stt.transcribe(audio) if audio is not None else ""
                    if not command:
                        print("(no command heard)")
                        continue
                    print(f"You  : {command}")
            else:
                # ---- hotkey mode ----
                if cut_off:
                    print("Listening...")
                    beep(settings)
                    audio = rec.record_until_silence()
                else:
                    print(f"\nPress {hotkey.upper()} and speak...")
                    audio = rec.record_push_to_talk(
                        hotkey, on_start=lambda: (print("Listening..."), beep(settings))
                    )
                was_cut_off, cut_off = cut_off, False
                if audio is None:
                    if not was_cut_off:
                        spk.speak("I didn't hear anything.")
                    continue
                command = stt.transcribe(audio)
                print(f"You  : {command}")
                if not command:
                    spk.speak("I didn't catch that.")
                    continue

            quit_now, interrupted = process(command)
            if quit_now:
                break
            if mode == "wake":
                if interrupted:
                    window = settings["command_wait_seconds"]
                elif settings["followup_seconds"] > 0:
                    window = settings["followup_seconds"]
            else:
                cut_off = interrupted

        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception as err:
            log.exception("loop error")
            print(f"[error] {err}")
            try:
                spk.speak("Something went wrong.")
            except Exception:
                pass
            window = None
            time.sleep(2)


if __name__ == "__main__":
    main()