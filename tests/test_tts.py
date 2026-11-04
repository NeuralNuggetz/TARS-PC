"""Phase 5 TTS tests. Run from the project root:  uv run python -m tests.test_tts"""
import time

from audio.tts import Speaker, clean_text

SAMPLE = (
    "## Latest AI news\n"
    "- **OpenAI** released a new model 🚀\n"
    "- See [the article](https://example.com/ai) for details\n"
    "Here is code: `print('hi')`\n"
    "```python\nprint('long code block')\n```"
)


def type_and_speak(spk):
    while True:
        text = input("Text to speak (Enter to go back): ").strip()
        if not text:
            return
        t0 = time.time()
        done = spk.speak(text)
        print(f"  engine={spk.last_engine}  completed={done}  total={time.time() - t0:.2f}s")


def cleaner_test():
    print("--- before ---")
    print(SAMPLE)
    print("--- after ---")
    print(clean_text(SAMPLE))


def force_offline(spk):
    spk._speak_offline("This is the offline fallback voice.")


def echo_test(spk):
    # Imported here so the other options work without the STT model loading
    from audio.recorder import Recorder
    from audio.stt import Transcriber

    stt = Transcriber()
    rec = Recorder()
    print("Echo test: press F9, speak, and TARS repeats you. Ctrl+C to stop.")
    try:
        while True:
            audio = rec.record_push_to_talk("f9")
            if audio is None:
                print("  (no speech detected)")
                continue
            text = stt.transcribe(audio)
            print(f"  Heard: {text!r}")
            if text:
                spk.speak(f"You said: {text}")   # mic is not recording while this blocks
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    spk = Speaker()
    while True:
        print("\n1) Type text and speak it")
        print("2) Cleaner test (markdown/URL/emoji removal)")
        print("3) Offline fallback voice")
        print("4) Echo test (F9 -> STT -> TTS)")
        print("q) Quit")
        choice = input("> ").strip().lower()
        if choice == "1":
            type_and_speak(spk)
        elif choice == "2":
            cleaner_test()
        elif choice == "3":
            force_offline(spk)
        elif choice == "4":
            echo_test(spk)
        elif choice == "q":
            break


if __name__ == "__main__":
    main()