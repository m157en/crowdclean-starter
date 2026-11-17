"""Non-destructive A/B previews of coarse shout boundaries.

This is broadband ducking, NOT voice separation. Music is attenuated too.
Only short previews are produced; the source mix is never modified.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path


def gain_at(t: float, start: float, end: float, *, gain: float = 0.25, fade: float = 0.25) -> float:
    """Smooth gain envelope with equal-length fade in/out."""
    if not (0 < gain <= 1 and fade > 0 and start < end):
        raise ValueError("Invalid gain envelope")
    if t <= start - fade or t >= end + fade:
        return 1.0
    if start - fade < t < start:
        u = (t - (start - fade)) / fade
        return 1 - (1 - gain) * (1 - math.cos(math.pi * u)) / 2
    if start <= t <= end:
        return gain
    u = (t - end) / fade
    return gain + (1 - gain) * (1 - math.cos(math.pi * u)) / 2


def duck_pcm(raw: bytes, rate: int, local_start: float, local_end: float, *, gain: float) -> bytes:
    if rate <= 0 or len(raw) % 2:
        raise ValueError("Expected 16-bit mono PCM")
    samples = array("h")
    samples.frombytes(raw)
    if os.sys.byteorder != "little":
        samples.byteswap()
    for i, sample in enumerate(samples):
        samples[i] = round(sample * gain_at(i / rate, local_start, local_end, gain=gain))
    if os.sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def write_wav(path: Path, raw: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(raw)


def create_previews(source: Path, dataset: Path, output: Path, *, gain: float = 0.25) -> list[dict]:
    if not source.is_file():
        raise FileNotFoundError(source)
    if not 0 < gain <= 1:
        raise ValueError("gain must be in (0, 1]")
    items = json.loads(dataset.read_text(encoding="utf-8"))["items"]
    targets = [item for item in items if item["decision"] == "remove"]
    if not targets or any("precise_boundary" not in item for item in targets):
        raise ValueError("All REMOVE items need precise_boundary")
    # Never overwrite prior experiments. Publish output directory only after all clips succeed.
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".crowdclean-preview-", dir=output.parent))
    try:
        report = []
        for item in targets:
            boundary = item["precise_boundary"]
            start, end = float(boundary["start"]), float(boundary["end"])
            clip_start, clip_end = float(item["start"]), float(item["end"])
            if not (0 <= clip_start <= start < end <= clip_end):
                raise ValueError(f"Invalid boundary for {item['file']}")
            name = Path(item["file"]).stem
            # 2 seconds of additional context on either side, capped at mix start.
            window_start = max(0.0, start - 2)
            window_end = end + 2
            command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-ss", str(window_start), "-i", str(source),
                       "-t", str(window_end - window_start), "-f", "s16le",
                       "-ac", "1", "-ar", "16000", "-"]
            raw = subprocess.run(command, check=True, capture_output=True).stdout
            if not raw:
                raise RuntimeError(f"No audio decoded for {name}")
            original = staging / f"{name}-original.wav"
            processed = staging / f"{name}-ducked.wav"
            write_wav(original, raw, 16000)
            write_wav(processed, duck_pcm(raw, 16000, start-window_start, end-window_start, gain=gain), 16000)
            report.append({"episode": name, "start": start, "end": end,
                           "original": original.name, "preview": processed.name,
                           "method": "broadband_ducking", "gain": gain})
        (staging / "report.json").write_text(json.dumps({
            "warning": "Broadband ducking reduces music along with voice; not vocal isolation or final cleaned mix.",
            "source": source.name, "items": report
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Directory rename on the same filesystem; destination checked again.
        if output.exists():
            raise FileExistsError(output)
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("storage/samples/lost-frequencies.mp3"))
    parser.add_argument("--dataset", type=Path, default=Path("datasets/lost-frequencies-review-threshold-03.json"))
    parser.add_argument("--output", type=Path, default=Path("storage/analysis/ab-preview-v1"))
    parser.add_argument("--gain", type=float, default=0.25)
    args = parser.parse_args()
    result = create_previews(args.source, args.dataset, args.output, gain=args.gain)
    print(json.dumps({"previews": len(result), "output": str(args.output),
                      "warning": "Music is also attenuated; original mix untouched."}, ensure_ascii=False))


if __name__ == "__main__":
    main()
