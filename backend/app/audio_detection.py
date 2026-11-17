"""Detect speech intervals in a WAV file using Silero VAD."""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from silero_vad import get_speech_timestamps, load_silero_vad


def detect_speech(
    audio_path: str | Path,
    *,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 100,
    speech_pad_ms: int = 30,
) -> dict:
    """Return speech intervals in seconds for a 16 kHz WAV file."""
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)

    if sample_rate != 16000:
        raise ValueError(
            f"Expected 16000 Hz audio, got {sample_rate} Hz. "
            "Convert the input to 16 kHz first."
        )

    # Silero VAD expects a mono, one-dimensional tensor.
    mono = samples.mean(axis=1, dtype=np.float32)
    audio = torch.from_numpy(np.ascontiguousarray(mono))

    model = load_silero_vad()
    timestamps = get_speech_timestamps(
        audio,
        model,
        threshold=threshold,
        sampling_rate=16000,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        speech_pad_ms=speech_pad_ms,
        return_seconds=True,
    )

    return {
        "source": str(path),
        "sample_rate": 16000,
        "detector": "silero-vad",
        "threshold": threshold,
        "speech_intervals": [
            {"start": round(item["start"], 3), "end": round(item["end"], 3)}
            for item in timestamps
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect speech intervals in a WAV file."
    )
    parser.add_argument("audio", type=Path, help="Input WAV file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("storage/analysis/speech.json"),
        help="Output JSON path",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    result = detect_speech(args.audio, threshold=args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Speech intervals found: {len(result['speech_intervals'])}")
    print(f"Result saved to: {args.output}")


if __name__ == "__main__":
    main()
