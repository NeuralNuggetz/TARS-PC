"""Phase 3: microphone capture with voice activity detection (VAD).

Output format is float32, mono, 16 kHz, which faster-whisper accepts directly.
"""
import collections
import time

import numpy as np
import sounddevice as sd
import webrtcvad

SAMPLE_RATE = 16000
FRAME_MS = 30                                  # webrtcvad accepts 10, 20 or 30 ms
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480 samples per frame


def list_input_devices():
    """Return (index, name) for every device that can record."""
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


class Recorder:
    def __init__(
        self,
        device=None,             # None = Windows default mic
        vad_mode=2,              # 0 = lenient ... 3 = strict (filters more noise)
        silence_ms=900,          # stop after this much silence once you have spoken
        max_seconds=15,          # hard stop
        no_speech_timeout=5,     # give up if nothing is said
        preroll_ms=300,          # audio kept from just before speech starts
        min_speech_ms=300,       # ignore blips shorter than this
    ):
        self.device = device
        self.vad = webrtcvad.Vad(vad_mode)
        self.silence_frames = silence_ms // FRAME_MS
        self.max_seconds = max_seconds
        self.no_speech_timeout = no_speech_timeout
        self.preroll_frames = preroll_ms // FRAME_MS
        self.min_speech_frames = min_speech_ms // FRAME_MS

    def record_until_silence(self):
        """Listen, start on first speech, stop after silence.

        Returns a float32 numpy array, or None if no speech was detected.
        """
        preroll = collections.deque(maxlen=self.preroll_frames)
        frames = []
        started = False
        speech_frames = 0
        silent_run = 0
        t0 = time.time()

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            channels=1,
            dtype="int16",
            device=self.device,
        ) as stream:
            while True:
                data, _overflowed = stream.read(FRAME_SAMPLES)
                frame = bytes(data)
                is_speech = self.vad.is_speech(frame, SAMPLE_RATE)
                elapsed = time.time() - t0

                if not started:
                    preroll.append(frame)
                    if is_speech:
                        started = True
                        frames.extend(preroll)
                        speech_frames = 1
                    elif elapsed > self.no_speech_timeout:
                        return None
                else:
                    frames.append(frame)
                    if is_speech:
                        speech_frames += 1
                        silent_run = 0
                    else:
                        silent_run += 1
                    if silent_run >= self.silence_frames:
                        break
                    if elapsed > self.max_seconds:
                        break

        if speech_frames < self.min_speech_frames:
            return None

        pcm = np.frombuffer(b"".join(frames), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0

    def record_fixed(self, seconds=5):
        """Record a fixed duration (for mic testing)."""
        audio = sd.rec(
            int(seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.device,
        )
        sd.wait()
        return audio.flatten()

    def record_push_to_talk(self, hotkey="f9"):
        """Block until the hotkey is pressed, then record until silence."""
        import keyboard  # imported here so other functions work without it

        keyboard.wait(hotkey)
        return self.record_until_silence()