"""Phase 4 STT tests. Run from the project root:  uv run python -m tests.test_stt"""
import soundfile as sf

from audio.recorder import SAMPLE_RATE, Recorder
from audio.stt import Transcriber


def live_loop(rec, stt):
    print("Press F9, speak a command, then pause. Ctrl+C to stop.\n")
    try:
        while True:
            print("Waiting for F9...")
            audio = rec.record_push_to_talk("f9")
            if audio is None:
                print("  (no speech detected)\n")
                continue
            text = stt.transcribe(audio)
            seconds = len(audio) / SAMPLE_RATE
            print(f"  Heard : {text!r}" if text else "  Heard : (empty / filtered)")
            print(f"  Audio : {seconds:.1f}s   Latency: {stt.last_latency:.2f}s\n")
    except KeyboardInterrupt:
        print("\nStopped.")


def from_file(stt):
    path = input("Path to .wav file (16 kHz mono works best): ").strip().strip('"')
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        print(f"Warning: file is {sr} Hz, expected {SAMPLE_RATE} Hz. Accuracy may drop.")
    print(f"Heard: {stt.transcribe(audio)!r}   ({stt.last_latency:.2f}s)")


def main():
    stt = Transcriber()          # change model_size here to compare models
    rec = Recorder()
    while True:
        print("\n1) Live: F9 push-to-talk -> transcript")
        print("2) Transcribe a .wav file")
        print("q) Quit")
        choice = input("> ").strip().lower()
        if choice == "1":
            live_loop(rec, stt)
        elif choice == "2":
            from_file(stt)
        elif choice == "q":
            break


if __name__ == "__main__":
    main()