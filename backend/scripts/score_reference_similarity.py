from pathlib import Path
import csv

import numpy as np
import soundfile as sf
import laion_clap

SOURCE = Path("storage/samples/area21-16k.wav")
REF_DIR = Path("storage/analysis/reference-16k")
OUT_DIR = Path("storage/analysis/reference-scan")
CLIP_DIR = OUT_DIR / "candidates"

POSITIVES = [REF_DIR / "crowd-positive-01.wav"]
NEGATIVES = [REF_DIR / "crowd-negative-02.wav"]

SAMPLE_RATE = 16000
WINDOW = 5.0
STEP = 0.5
SCAN_START = 160.0
SCAN_END = 180.0


def main():
    for path in [SOURCE, *POSITIVES, *NEGATIVES]:
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

    if not POSITIVES:
        raise RuntimeError("No positive reference files found")

    if not NEGATIVES:
        raise RuntimeError("No negative reference files found")

    audio, sr = sf.read(SOURCE, dtype="float32")

    if sr != SAMPLE_RATE:
        raise ValueError(f"Expected {SAMPLE_RATE} Hz, got {sr}")

    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    duration = len(audio) / sr
    window_samples = int(WINDOW * sr)
    last_start = min(SCAN_END - WINDOW, duration - WINDOW)

    if last_start < SCAN_START:
        raise ValueError("Source audio is shorter than the requested scan")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    candidates = []
    starts = np.round(
        np.arange(SCAN_START, last_start + 0.001, STEP), 2
    )

    for number, start in enumerate(starts, start=1):
        first = int(round(start * sr))
        clip = audio[first:first + window_samples]

        if len(clip) != window_samples:
            continue

        path = CLIP_DIR / f"candidate-{number:03d}-{start:.1f}.wav"
        sf.write(path, clip, sr)
        candidates.append((float(start), path))

    # Порядок: положительные эталоны, отрицательные эталоны, кандидаты.
    files = [*POSITIVES, *NEGATIVES, *(path for _, path in candidates)]

    print(f"Positive references: {len(POSITIVES)}")
    print(f"Negative references: {len(NEGATIVES)}")
    print(f"Candidate windows: {len(candidates)}")
    print("Loading CLAP model...")

    model = laion_clap.CLAP_Module(
        enable_fusion=False,
        device="cpu",
    )
    model.load_ckpt()

    embeddings = model.get_audio_embedding_from_filelist(
        x=[str(path) for path in files],
        use_tensor=False,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("CLAP returned a zero-length embedding")

    embeddings /= norms

    positive_count = len(POSITIVES)
    negative_start = positive_count
    candidate_start = positive_count + len(NEGATIVES)
    positive_embeddings = embeddings[:positive_count]
    negative_embeddings = embeddings[negative_start:candidate_start]
    candidate_embeddings = embeddings[candidate_start:]

    rows = []

    for i, (start, path) in enumerate(candidates):
        positive_scores = candidate_embeddings[i] @ positive_embeddings.T
        positive_score = float(np.max(positive_scores))
        negative_scores = candidate_embeddings[i] @ negative_embeddings.T
        best_negative_index = int(np.argmax(negative_scores))
        negative_score = float(negative_scores[best_negative_index])

        rows.append({
            "start_seconds": round(start, 2),
            "end_seconds": round(start + WINDOW, 2),
            "positive_similarity": round(positive_score, 4),
            "negative_similarity": round(negative_score, 4),
            "negative_reference": NEGATIVES[best_negative_index].name,
            "negative_minus_positive": round(
                negative_score - positive_score, 4
            ),
            "candidate_file": path.name,
        })

    rows.sort(
        key=lambda row: row["negative_minus_positive"],
        reverse=True,
    )

    report = OUT_DIR / "scores.csv"
    with report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("\nTop 10 windows closest to unwanted audio:")
    for row in rows[:10]:
        print(
            f'{row["start_seconds"]:6.2f}-{row["end_seconds"]:6.2f}s '
            f'positive={row["positive_similarity"]:.4f} '
            f'negative={row["negative_similarity"]:.4f} '
            f'margin={row["negative_minus_positive"]:+.4f}'
        )

    print("\nWindows around the known DJ shout:")
    for row in sorted(rows, key=lambda r: r["start_seconds"]):
        if 170.0 <= row["start_seconds"] <= 174.0:
            print(
                f'{row["start_seconds"]:6.2f}-{row["end_seconds"]:6.2f}s '
                f'margin={row["negative_minus_positive"]:+.4f} '
                f'ref={row["negative_reference"]}'
            )

    print(f"\nFull report saved to: {report}")


if __name__ == "__main__":
    main()
