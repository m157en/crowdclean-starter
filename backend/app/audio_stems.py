"""Experimental vocal-stem suppression on short annotated clips only.

Requires optional Demucs CLI, ffmpeg and numpy/soundfile. Does not modify source.
No inference is run on import; install and model download are explicit local steps.
"""
import argparse
import json
import importlib.util
import sys
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from app.audio_preview import gain_at


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def validate_target(item: dict) -> tuple[float, float, float, float]:
    boundary = item["precise_boundary"]
    start, end = float(boundary["start"]), float(boundary["end"])
    clip_start, clip_end = float(item["start"]), float(item["end"])
    if not all(math.isfinite(v) for v in (start, end, clip_start, clip_end)):
        raise ValueError("Non-finite audio time")
    if not 0 <= clip_start <= start < end <= clip_end:
        raise ValueError("Boundary outside review interval")
    return start, end, max(0.0, start - 2), end + 2


def suppress_vocals(vocals: np.ndarray, instrumental: np.ndarray, rate: int,
                    start: float, end: float, *, gain: float = 0.0,
                    fade: float = 0.25) -> np.ndarray:
    """Blend stems, attenuating only vocal stem inside human-annotated boundary."""
    if vocals.shape != instrumental.shape or vocals.ndim != 2 or vocals.shape[1] != 2:
        raise ValueError("Expected aligned stereo stems")
    if rate <= 0 or not 0 <= gain <= 1 or not 0 < start < end or fade <= 0:
        raise ValueError("Invalid stem mix parameters")
    times = np.arange(len(vocals), dtype=np.float64) / rate
    envelope = np.ones(len(vocals), dtype=np.float32)
    fade_in = (times > start - fade) & (times < start)
    fade_out = (times > end) & (times < end + fade)
    envelope[fade_in] = 1 - (1 - gain) * (1 - np.cos(np.pi * (times[fade_in] - (start - fade)) / fade)) / 2
    envelope[(times >= start) & (times <= end)] = gain
    envelope[fade_out] = gain + (1 - gain) * (1 - np.cos(np.pi * (times[fade_out] - end) / fade)) / 2
    return instrumental + vocals * envelope[:, None]


def create_stem_previews(source: Path, dataset: Path, output: Path, *,
                         model: str = "htdemucs", gain: float = 0.0,
                         limit: int = 2) -> list[dict]:
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    if not 0 <= gain <= 1 or not 1 <= limit <= 8:
        raise ValueError("Invalid gain or limit")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required")
    if importlib.util.find_spec("demucs") is None:
        raise RuntimeError("Demucs is not installed in this Python environment")
    items = json.loads(dataset.read_text(encoding="utf-8"))["items"]
    targets = [item for item in items if item["decision"] == "remove"][:limit]
    if not targets:
        raise ValueError("No REMOVE episodes")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crowdclean-stems-", dir=output.parent) as temp:
        workspace = Path(temp)
        staging = workspace / "results"
        staging.mkdir()
        report = []
        for item in targets:
            start, end, window_start, window_end = validate_target(item)
            name = Path(item["file"]).stem
            if not name.startswith("review-") or Path(item["file"]).name != item["file"]:
                raise ValueError("Invalid episode name")
            decoded = workspace / f"{name}.wav"
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-ss", str(window_start), "-i", str(source),
                 "-t", str(window_end-window_start), "-ar", "44100",
                 "-ac", "2", "-c:a", "pcm_f32le", str(decoded)])
            separated = workspace / "separated"
            run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", model,
                 "-o", str(separated), str(decoded)])
            stems = separated / model / name
            vocals, vr = sf.read(stems / "vocals.wav", dtype="float32", always_2d=True)
            instrumental, ir = sf.read(stems / "no_vocals.wav", dtype="float32", always_2d=True)
            if vr != ir or vr != 44100 or vocals.shape != instrumental.shape:
                raise ValueError("Separator stems do not align")
            original, original_rate = sf.read(decoded, dtype="float32", always_2d=True)
            if original_rate != vr:
                raise ValueError("Original sample rate mismatch")
            # Demucs may pad a few frames; output matches original clip duration.
            count = min(len(original), len(vocals))
            if count == 0:
                raise ValueError("Empty stems")
            processed = suppress_vocals(vocals[:count], instrumental[:count], vr,
                                        start-window_start, end-window_start, gain=gain)
            peak = float(np.max(np.abs(processed)))
            if not math.isfinite(peak):
                raise ValueError("Non-finite output")
            # Do not normalize: changes in level must remain audible for comparison.
            sf.write(staging / f"{name}-original.wav", original[:count], vr, subtype="PCM_16")
            sf.write(staging / f"{name}-stems.wav", np.clip(processed, -1, 1), vr, subtype="PCM_16")
            report.append({"episode": name, "start": start, "end": end,
                           "original": f"{name}-original.wav", "preview": f"{name}-stems.wav",
                           "method": "demucs_vocal_stem_attenuation", "model": model,
                           "vocal_gain": gain, "peak_before_clipping": peak})
        (staging / "report.json").write_text(json.dumps({
            "source": source.name, "items": report,
            "warning": "Experimental vocal stem attenuation; may damage sung vocals and instruments. Not a clean mix."
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if output.exists():
            raise FileExistsError(output)
        staging.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("storage/samples/lost-frequencies.mp3"))
    parser.add_argument("--dataset", type=Path, default=Path("datasets/lost-frequencies-review-threshold-03.json"))
    parser.add_argument("--output", type=Path, default=Path("storage/analysis/ab-stems-v1"))
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--gain", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    report = create_stem_previews(args.source, args.dataset, args.output,
                                  model=args.model, gain=args.gain, limit=args.limit)
    print(json.dumps({"previews": len(report), "output": str(args.output),
                      "warning": "Experimental stem separation; original untouched."}))


if __name__ == "__main__":
    main()
