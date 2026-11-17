from pathlib import Path
import csv
import tempfile

import numpy as np
import soundfile as sf
import laion_clap
from scipy.signal import resample_poly
from math import gcd

REF_DIR = Path("storage/analysis/reference-16k")
TEST_DIR = Path("storage/analysis/review/lost-frequencies")
OUT_DIR = Path("storage/analysis/reference-scan")

# positive = обычная музыка, которую сохраняем
# negative = DJ shout-out, который удаляем
POSITIVES = [REF_DIR / "crowd-positive-01.wav"]
NEGATIVES = [REF_DIR / "crowd-negative-02.wav"]

TEST_CLIPS = [
    TEST_DIR / "candidate-204.wav",
    TEST_DIR / "candidate-421.wav",
]

TARGET_SR = 16000
WINDOW_SEC = 1.0
STEP_SEC = 0.25


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


def main():
    all_required = POSITIVES + NEGATIVES + TEST_CLIPS
    missing = [str(p) for p in all_required if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing files:\n" + "\n".join(missing)
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "external-test-windows.csv"

    window_samples = int(WINDOW_SEC * TARGET_SR)
    step_samples = int(STEP_SEC * TARGET_SR)

    with tempfile.TemporaryDirectory(prefix="crowdclean-windows-") as tmp:
        tmp_dir = Path(tmp)
        window_files = []
        window_info = []

        for clip in TEST_CLIPS:
            audio = load_mono_16k(clip)

            if len(audio) < window_samples:
                raise ValueError(
                    f"{clip} is shorter than {WINDOW_SEC} second"
                )

            starts = range(
                0,
                len(audio) - window_samples + 1,
                step_samples,
            )

            for index, start in enumerate(starts):
                end = start + window_samples
                window_path = tmp_dir / (
                    f"{clip.stem}_window_{index:03d}.wav"
                )

                sf.write(
                    window_path,
                    audio[start:end],
                    TARGET_SR,
                    subtype="PCM_16",
                )

                window_files.append(window_path)
                window_info.append({
                    "test_clip": clip.name,
                    "window_start_sec": round(start / TARGET_SR, 2),
                    "window_end_sec": round(end / TARGET_SR, 2),
                })

        files_to_score = POSITIVES + NEGATIVES + window_files

        print(f"Positive references (KEEP): {len(POSITIVES)}")
        print(f"Negative references (REMOVE): {len(NEGATIVES)}")
        print(f"Test windows: {len(window_files)}")
        print("Loading CLAP model...")

        model = laion_clap.CLAP_Module(
            enable_fusion=False,
            device="cpu",
        )
        model.load_ckpt()

        embeddings = model.get_audio_embedding_from_filelist(
            x=[str(p) for p in files_to_score],
            use_tensor=False,
        )
        embeddings = np.asarray(embeddings, dtype=np.float32)

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise RuntimeError("CLAP returned a zero-length embedding")
        embeddings /= norms

        p_count = len(POSITIVES)
        n_count = len(NEGATIVES)

        positive_embedding = embeddings[0]
        negative_embedding = embeddings[p_count]

        window_embeddings = embeddings[p_count + n_count:]
        rows = []

        for info, embedding in zip(window_info, window_embeddings):
            p_score = float(embedding @ positive_embedding)
            n_score = float(embedding @ negative_embedding)
            margin = n_score - p_score

            if margin > 0:
                closer_class = "negative"
            elif margin < 0:
                closer_class = "positive"
            else:
                closer_class = "tie"

            rows.append({
                **info,
                "positive_similarity": round(p_score, 4),
                "negative_similarity": round(n_score, 4),
                "negative_minus_positive": round(margin, 4),
                "closer_class": closer_class,
            })

        fields = [
            "test_clip",
            "window_start_sec",
            "window_end_sec",
            "positive_similarity",
            "negative_similarity",
            "negative_minus_positive",
            "closer_class",
        ]

        with report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        print("\nWindow scores:")
        for row in rows:
            print(
                f'{row["test_clip"]:24} '
                f'{row["window_start_sec"]:5.2f}-'
                f'{row["window_end_sec"]:5.2f}s | '
                f'KEEP={row["positive_similarity"]:.4f} '
                f'REMOVE={row["negative_similarity"]:.4f} '
                f'MARGIN={row["negative_minus_positive"]:+.4f} | '
                f'{row["closer_class"]}'
            )

        print(f"\nCSV report saved to: {report}")


if __name__ == "__main__":
    main()
