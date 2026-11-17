from pathlib import Path
import csv
import tempfile
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
import laion_clap

REVIEW_DIR = Path("storage/analysis/review/lost-frequencies")
CLEAN_DIR = REVIEW_DIR / "clean-candidates"
OUT_DIR = Path("storage/analysis/reference-scan")

TARGET_SR = 16000
WINDOW_SEC = 1.0
STEP_SEC = 0.25

REMOVE_PROMPTS = [
    "A DJ speaking to the crowd over loud electronic dance music.",
    "A DJ shouting to hype up the audience at a live music festival.",
    "A spoken announcement by a DJ over a dance music track.",
]

KEEP_PROMPTS = [
    "Electronic dance music with instrumental synthesizers and a beat.",
    "An electronic dance music track with melodic sung vocals.",
    "A live electronic music performance with music playing and no speech.",
]


def load_mono_16k(path):
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)

    if sr != TARGET_SR:
        divisor = gcd(int(sr), TARGET_SR)
        audio = resample_poly(
            audio,
            TARGET_SR // divisor,
            int(sr) // divisor,
        ).astype(np.float32)

    return audio


def normalize(embeddings):
    embeddings = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)

    if np.any(norms == 0):
        raise RuntimeError("CLAP returned a zero-length embedding")

    return embeddings / norms


def main():
    test_clips = [
        (path, "REMOVE")
        for path in sorted(REVIEW_DIR.glob("candidate-*.wav"))
    ]
    test_clips += [
        (path, "KEEP")
        for path in sorted(CLEAN_DIR.glob("clean-*.wav"))
    ]

    if not test_clips:
        raise RuntimeError("No test clips found")

    print("Test clips:")
    for path, label in test_clips:
        print(f"  {path.name}: {label}")

    window_samples = int(WINDOW_SEC * TARGET_SR)
    step_samples = int(STEP_SEC * TARGET_SR)

    window_info = []

    with tempfile.TemporaryDirectory(prefix="crowdclean-labeled-") as tmp:
        tmp_dir = Path(tmp)
        window_files = []

        for clip, ground_truth in test_clips:
            audio = load_mono_16k(clip)

            if len(audio) < window_samples:
                print(f"Skipping short clip: {clip.name}")
                continue

            for index, start in enumerate(
                range(0, len(audio) - window_samples + 1, step_samples)
            ):
                end = start + window_samples
                path = tmp_dir / f"{clip.stem}_{index:03d}.wav"

                sf.write(
                    path,
                    audio[start:end],
                    TARGET_SR,
                    subtype="PCM_16",
                )
                window_files.append(path)

                window_info.append({
                    "test_clip": clip.name,
                    "ground_truth": ground_truth,
                    "window_start_sec": round(start / TARGET_SR, 2),
                    "window_end_sec": round(end / TARGET_SR, 2),
                })

        print(f"\nTotal windows: {len(window_files)}")
        print("Loading CLAP model...")

        model = laion_clap.CLAP_Module(
            enable_fusion=False,
            device="cpu",
        )
        model.load_ckpt()

        audio_embeddings = normalize(
            model.get_audio_embedding_from_filelist(
                x=[str(p) for p in window_files],
                use_tensor=False,
            )
        )

        keep_embeddings = normalize(
            model.get_text_embedding(KEEP_PROMPTS, use_tensor=False)
        )
        remove_embeddings = normalize(
            model.get_text_embedding(REMOVE_PROMPTS, use_tensor=False)
        )

        keep_scores = audio_embeddings @ keep_embeddings.T
        remove_scores = audio_embeddings @ remove_embeddings.T

        rows = []

        for i, info in enumerate(window_info):
            keep = float(np.mean(keep_scores[i]))
            remove = float(np.mean(remove_scores[i]))
            margin = remove - keep

            rows.append({
                **info,
                "text_keep_similarity": round(keep, 4),
                "text_remove_similarity": round(remove, 4),
                "remove_minus_keep": round(margin, 4),
                "prediction": (
                    "REMOVE" if margin > 0
                    else "KEEP" if margin < 0
                    else "TIE"
                ),
            })

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        report = OUT_DIR / "labeled-test-text-scores.csv"

        fields = [
            "test_clip",
            "ground_truth",
            "window_start_sec",
            "window_end_sec",
            "text_keep_similarity",
            "text_remove_similarity",
            "remove_minus_keep",
            "prediction",
        ]

        with report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        print("\n=== PER-CLIP SUMMARY ===")

        for clip, ground_truth in test_clips:
            clip_rows = [
                row for row in rows
                if row["test_clip"] == clip.name
            ]

            if not clip_rows:
                continue

            predicted_remove = sum(
                row["prediction"] == "REMOVE"
                for row in clip_rows
            )
            total = len(clip_rows)
            rate = predicted_remove / total * 100
            max_margin = max(
                row["remove_minus_keep"] for row in clip_rows
            )

            print(
                f"{clip.name:24} "
                f"TRUE={ground_truth:6} "
                f"REMOVE_WINDOWS={predicted_remove}/{total} "
                f"({rate:.1f}%) "
                f"MAX_MARGIN={max_margin:+.4f}"
            )

        print("\n=== WINDOW RESULTS ===")

        for row in rows:
            print(
                f'{row["test_clip"]:24} '
                f'{row["window_start_sec"]:5.2f}-'
                f'{row["window_end_sec"]:5.2f}s | '
                f'KEEP={row["text_keep_similarity"]:.4f} '
                f'REMOVE={row["text_remove_similarity"]:.4f} '
                f'MARGIN={row["remove_minus_keep"]:+.4f} | '
                f'TRUE={row["ground_truth"]:6} '
                f'PRED={row["prediction"]}'
            )

        print(f"\nCSV report saved to: {report}")


if __name__ == "__main__":
    main()
