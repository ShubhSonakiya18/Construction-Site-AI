"""
scripts/create_sample_audio.py — Generate synthetic WAV files for testing.

Real foreman voice recordings cannot be committed to the repository (binary
files, no consistent source, may be gitignored). This script generates 10
synthetic sine-tone WAV files that exercise the validation and pipeline code
paths without requiring real audio.

These files are NOT useful for testing transcription accuracy (sine tones
have no speech content). They are useful for:
- Validator boundary tests (duration, sample rate, channels, format)
- Pipeline integration tests
- CLI smoke testing

For real transcription quality testing (WER), drop real WAV recordings into
data/sample_audio/ alongside a matching .txt ground-truth file with the same
stem name. See data/sample_audio/README.md.

Usage:
    python scripts/create_sample_audio.py
    python scripts/create_sample_audio.py --output-dir data/sample_audio
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False


# (filename_stem, duration_seconds, frequency_hz, sample_rate, channels)
SAMPLE_SPECS: list[tuple[str, float, float, int, int]] = [
    ("sample_01_short_tone", 1.0, 440.0, 16000, 1),
    ("sample_02_medium_tone", 5.0, 440.0, 16000, 1),
    ("sample_03_long_tone", 15.0, 440.0, 16000, 1),
    ("sample_04_low_freq", 5.0, 220.0, 16000, 1),
    ("sample_05_high_freq", 5.0, 880.0, 16000, 1),
    ("sample_06_stereo", 5.0, 440.0, 16000, 2),
    ("sample_07_low_samplerate", 5.0, 440.0, 8000, 1),
    ("sample_08_high_samplerate", 5.0, 440.0, 44100, 1),
    ("sample_09_very_short", 0.6, 440.0, 16000, 1),
    ("sample_10_chunk_boundary", 35.0, 440.0, 16000, 1),
]

GROUND_TRUTH_PLACEHOLDER = (
    "[PLACEHOLDER] This is a synthetic sine-tone file with no real speech "
    "content. Replace this file's matching .wav with a real recording and "
    "this .txt with its ground-truth transcript for WER testing."
)


def make_sine_wav(path: Path, duration_seconds: float, frequency_hz: float,
                  sample_rate: int, channels: int) -> None:
    num_samples = int(duration_seconds * sample_rate)

    if HAS_NUMPY and HAS_SOUNDFILE:
        t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
        tone = (np.sin(2 * np.pi * frequency_hz * t) * 0.5).astype(np.float32)
        if channels == 2:
            audio = np.stack([tone, tone * 0.8], axis=1)
        else:
            audio = tone
        sf.write(str(path), audio, sample_rate, subtype="PCM_16")
        return

    # Fallback: stdlib wave module, silence if numpy unavailable
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        if HAS_NUMPY:
            t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
            tone = (np.sin(2 * np.pi * frequency_hz * t) * 16383).astype(np.int16)
            if channels == 2:
                frames = np.stack([tone, tone], axis=1).tobytes()
            else:
                frames = tone.tobytes()
            wf.writeframes(frames)
        else:
            wf.writeframes(b"\x00" * num_samples * channels * 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", default="data/sample_audio",
        help="Directory to write generated WAV files (default: data/sample_audio)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not HAS_NUMPY:
        print("WARNING: numpy not installed. Generated files will be silence, "
              "not sine tones. Run: pip install numpy soundfile")

    print(f"Generating {len(SAMPLE_SPECS)} synthetic audio files in {out_dir}/")

    for stem, duration, freq, rate, channels in SAMPLE_SPECS:
        wav_path = out_dir / f"{stem}.wav"
        txt_path = out_dir / f"{stem}.txt"

        make_sine_wav(wav_path, duration, freq, rate, channels)
        txt_path.write_text(GROUND_TRUTH_PLACEHOLDER, encoding="utf-8")

        print(f"  OK  {wav_path.name}  ({duration}s, {freq}Hz, {rate}Hz sample rate, {channels}ch)")

    print(f"\nDone. {len(SAMPLE_SPECS)} WAV files + ground-truth placeholders written.")
    print("These are synthetic sine tones, not real speech.")
    print("Drop real recordings into data/sample_audio/ for transcription quality testing.")


if __name__ == "__main__":
    main()
