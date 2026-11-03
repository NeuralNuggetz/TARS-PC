"""Phase 3 mic tests. Run from the project root:  python -m tests.test_audio"""
import os

import sounddevice as sd
import soundfile as sf

from audio.recorder import SAMPLE_RATE, Recorder, list_input_devices

OUT_DIR = "logs"
os.makedirs(OUT_DIR, exist_ok=True)


def save_and_play(audio, name):
    path = os.path.join(OUT_DIR, name)
    sf.write(path, audio, SAMPLE_RATE)
    print(f"Saved {path}  ({len(audio) / SAMPLE_RATE:.1f}s). Playing back...")
    sd.play(audio, SAMPLE_RATE)
    sd.wait()


def pick_device():
    devices = list_input_devices()
    print("\nInput devices:")
    for i, name in devices:
        print(f"  [{i}] {name}")
    choice = input("Device index (Enter = default): ").strip()
    return int(choice) if choice else None


def main():
    device = None
    while True:
        print("\n1) List and pick mic")
        print("2) Record 5 seconds and play back")
        print("3) Speak once (auto-stop on silence) and play back")
        print("4) Push-to-talk loop (F9, Ctrl+C to quit)")
        print("q) Quit")
        choice = input("> ").strip().lower()
        rec = Recorder(device=device)

        if choice == "1":
            device = pick_device()
        elif choice == "2":
            print("Recording 5s... speak now")
            save_and_play(rec.record_fixed(5), "fixed_test.wav")
        elif choice == "3":
            print("Speak now...")
            audio = rec.record_until_silence()
            if audio is None:
                print("No speech detected.")
            else:
                save_and_play(audio, "vad_test.wav")
        elif choice == "4":
            print("Press F9, then speak.")
            try:
                while True:
                    audio = rec.record_push_to_talk("f9")
                    if audio is None:
                        print("No speech detected.")
                    else:
                        save_and_play(audio, "ptt_test.wav")
                    print("Press F9 again...")
            except KeyboardInterrupt:
                print("\nStopped.")
        elif choice == "q":
            break


if __name__ == "__main__":
    main()