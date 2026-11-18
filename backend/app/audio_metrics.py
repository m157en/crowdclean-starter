"""Offline objective screening for CrowdClean A/B previews.

Measures attenuation and collateral audio damage. It does NOT identify a DJ
voice or establish perceptual quality without clean reference stems.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float64))))) if samples.size else 0.0


def db_ratio(numerator: float, denominator: float) -> float:
    return float(20 * np.log10(max(numerator, 1e-10) / max(denominator, 1e-10)))


def analyze_pair(original: np.ndarray, processed: np.ndarray, rate: int,
                 local_start: float, local_end: float) -> dict:
    if original.shape != processed.shape or original.ndim != 2 or original.shape[1] not in (1, 2):
        raise ValueError("Original and processed audio must have aligned mono/stereo samples")
    if rate <= 0 or not 0 <= local_start < local_end <= len(original) / rate + 1 / rate:
        raise ValueError("Invalid rate or boundary")
    if not np.all(np.isfinite(original)) or not np.all(np.isfinite(processed)):
        raise ValueError("Non-finite audio")
    times = np.arange(len(original)) / rate
    inside = (times >= local_start) & (times < local_end)
    outside = (times < local_start - 0.3) | (times >= local_end + 0.3)
    if not inside.any() or not outside.any():
        raise ValueError("Need target and context audio")
    difference = processed.astype(np.float64) - original.astype(np.float64)
    original_inside = rms(original[inside])
    processed_inside = rms(processed[inside])
    context = rms(original[outside])
    context_error = rms(difference[outside])
    return {
        "target_level_change_db": round(db_ratio(processed_inside, original_inside), 2),
        "context_error_relative_db": round(db_ratio(context_error, context), 2),
        "context_rms_error": round(context_error, 7),
        "target_rms_error": round(rms(difference[inside]), 7),
        "processed_peak": round(float(np.max(np.abs(processed))), 5),
        "clipped_samples": int(np.count_nonzero(np.abs(processed) >= 0.9999)),
        "interpretation": "Target level change is not a DJ-vocal isolation score; context error is not perceptual quality.",
    }


def evaluate(folder: Path, *, source_dataset: Path | None = None) -> dict:
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    boundaries = {}
    if source_dataset is not None:
        data = json.loads(source_dataset.read_text(encoding="utf-8"))
        boundaries = {Path(item["file"]).stem: item for item in data["items"]}
    results = []
    for item in report["items"]:
        original, rate = sf.read(folder / item["original"], dtype="float32", always_2d=True)
        processed, processed_rate = sf.read(folder / item["preview"], dtype="float32", always_2d=True)
        if rate != processed_rate:
            raise ValueError("Sample rates differ")
        episode = item["episode"]
        if episode in boundaries:
            start = float(boundaries[episode]["precise_boundary"]["start"])
            end = float(boundaries[episode]["precise_boundary"]["end"])
        else:
            start, end = float(item["start"]), float(item["end"])
        # Preview generation always begins 2 seconds before annotated boundary,
        # except at time zero.
        window_start = max(0.0, start - 2.0)
        metrics = analyze_pair(original, processed, rate, start - window_start, end - window_start)
        results.append({"episode": episode, **metrics})
    return {"method": report["items"][0].get("method") if results else None,
            "evaluated": len(results), "items": results,
            "status": "SCREENING_ONLY",
            "limitations": ["No clean DJ-only reference or reliable vocal identity",
                            "No validated perceptual music quality score",
                            "Cannot automatically certify shout removal"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=Path("storage/analysis/ab-preview-v1"))
    parser.add_argument("--dataset", type=Path, default=Path("datasets/lost-frequencies-review-threshold-03.json"))
    args = parser.parse_args()
    result = evaluate(args.folder, source_dataset=args.dataset)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
