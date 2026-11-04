"""Phase 4: speech-to-text with faster-whisper.

Input:  float32 mono 16 kHz numpy array (what audio.recorder returns)
Output: cleaned transcript string ("" if nothing useful was heard)
"""
import os
import sys
import time
from pathlib import Path

import numpy as np


def _register_nvidia_dlls():
    """Windows: let Python find CUDA libs installed via pip
    (nvidia-cublas-cu12, nvidia-cudnn-cu12). Must run before faster_whisper loads."""
    if os.name != "nt":
        return
    for base in map(Path, sys.path):
        nvidia = base / "nvidia"
        if nvidia.is_dir():
            for bin_dir in nvidia.glob("*/bin"):
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


_register_nvidia_dlls()

from faster_whisper import WhisperModel  # noqa: E402

# Hint text helps Whisper spell your app names correctly.
# Add your own apps and words here.
DEFAULT_PROMPT = (
    "Voice commands for a Windows PC assistant named TARS. "
    "Apps: VS Code, Chrome, Notepad, Calculator, File Explorer. "
    "Sites: YouTube, GitHub, Google."
)

# Whisper often invents these phrases from silence or noise.
HALLUCINATIONS = {
    "you",
    "thank you",
    "thanks",
    "thanks for watching",
    "thank you for watching",
    "bye",
    "okay",
}


def _pick_device():
    """Use the GPU if CUDA is available, otherwise CPU."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class Transcriber:
    def __init__(
        self,
        model_size="base.en",   # try "small.en" for better accuracy, "small" for multilingual
        language="en",          # None = auto-detect (needs a multilingual model)
        prompt=DEFAULT_PROMPT,
        beam_size=1,            # 1 = fastest, 5 = more accurate
        device="auto",          # "auto", "cpu" or "cuda"
    ):
        self.language = language
        self.prompt = prompt
        self.beam_size = beam_size
        self.last_latency = 0.0
        self.model_size = model_size

        if device == "auto":
            device, compute_type = _pick_device()
        else:
            compute_type = "float16" if device == "cuda" else "int8"

        self._load(device, compute_type)

        # CUDA can be detected yet fail at first use (missing cuBLAS/cuDNN DLLs).
        # Warm up once and fall back to CPU instead of crashing later.
        if device == "cuda":
            try:
                self._warmup()
            except RuntimeError as err:
                print(f"[stt] GPU failed ({err}). Falling back to CPU.")
                self._load("cpu", "int8")

    def _load(self, device, compute_type):
        print(f"[stt] loading '{self.model_size}' on {device} ({compute_type})...")
        t0 = time.time()
        self.model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
        self.device = device
        print(f"[stt] model ready in {time.time() - t0:.1f}s")

    def _warmup(self):
        silence = np.zeros(16000, dtype=np.float32)
        segments, _ = self.model.transcribe(silence, language=self.language, vad_filter=False)
        list(segments)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""

        t0 = time.time()
        segments, _info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.prompt,
            vad_filter=True,                    # drop silence inside the clip
            condition_on_previous_text=False,   # avoids repeated-text loops
        )

        parts = []
        for seg in segments:  # generator: decoding happens here
            # Skip segments Whisper itself is unsure are speech.
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            parts.append(seg.text.strip())

        self.last_latency = time.time() - t0
        text = " ".join(parts).strip()

        if text.lower().strip(" .!?,") in HALLUCINATIONS:
            return ""
        return text