"""Chunked speech candidate detection for CrowdClean."""

import argparse
import json
import tempfile
import wave
from pathlib import Path

from app.audio_preprocessing import prepare_audio


def load_silero_vad():
    """Load the speech model only for a real inference job."""
    from silero_vad import load_silero_vad as load
    return load()


def get_speech_timestamps(audio, model, **kwargs):
    """Convert NumPy chunks to Torch only at the inference boundary."""
    import torch
    from silero_vad import get_speech_timestamps as detect
    return detect(torch.from_numpy(audio), model, **kwargs)


def merge_intervals(intervals, tolerance=0.15):
    merged = []
    for interval in sorted(intervals, key=lambda x: x["start"]):
        start, end = interval["start"], interval["end"]
        if merged and start <= merged[-1]["end"] + tolerance:
            merged[-1]["end"] = max(merged[-1]["end"], end)
        else:
            merged.append({"start": start, "end": end})
    return merged


def analyze_wav(path, *, chunk_seconds=30, overlap_seconds=1, threshold=0.3):
    path = Path(path)
    if chunk_seconds <= overlap_seconds or overlap_seconds < 0:
        raise ValueError("Invalid chunk/overlap configuration")

    # Inference-only dependencies must not be imported by API/test collection.
    import numpy as np

    model = load_silero_vad()
    intervals = []

    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        if rate != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Expected mono 16 kHz 16-bit WAV")

        total_frames = wav.getnframes()
        chunk_frames = int(chunk_seconds * rate)
        overlap_frames = int(overlap_seconds * rate)
        step = chunk_frames - overlap_frames

        if step <= 0:
            raise ValueError("Invalid chunk size")

        for start_frame in range(0, total_frames, step):
            wav.setpos(start_frame)
            raw = wav.readframes(chunk_frames)
            if not raw:
                break

            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            audio = samples

            stamps = get_speech_timestamps(
                audio, model, sampling_rate=16000,
                return_seconds=True,
                threshold=threshold,
            )

            offset = start_frame / rate
            for stamp in stamps:
                intervals.append({
                    "start": round(offset + stamp["start"], 3),
                    "end": round(offset + stamp["end"], 3),
                })

    return {
        "source": str(path),
        "detector": "silero-vad",
        "status": "pending_review",
        "speech_intervals": merge_intervals(intervals),
    }


def analyze_audio(source, output):
    source = Path(source).resolve()
    output = Path(output).resolve()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="crowdclean-analysis-",
        dir=output.parent,
    ) as temporary_dir:
        prepared = Path(temporary_dir) / "analysis.wav"
        metadata = prepare_audio(source, prepared)
        result = analyze_wav(prepared)
        result["source"] = str(source)
        result["duration_seconds"] = metadata["duration_seconds"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = analyze_audio(args.source, args.output)
    print(json.dumps({
        "intervals": len(result["speech_intervals"]),
        "duration_seconds": result["duration_seconds"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
