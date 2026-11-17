from pathlib import Path
import csv

import numpy as np
import laion_clap

REF_DIR = Path("storage/analysis/reference-16k")
TEST_DIR = Path("storage/analysis/review/lost-frequencies")
OUT_DIR = Path("storage/analysis/reference-scan")

POSITIVES = [REF_DIR / "crowd-positive-01.wav"]
NEGATIVES = [REF_DIR / "crowd-negative-02.wav"]
TEST_CLIPS = [
    TEST_DIR / "candidate-204.wav",
    TEST_DIR / "candidate-421.wav",
]

def main():
    files_to_check = [*POSITIVES, *NEGATIVES, *TEST_CLIPS]

    missing = [str(p) for p in files_to_check if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing files:\n" + "\n".join(missing)
        )

    if not POSITIVES or not NEGATIVES:
        raise RuntimeError("Both positive and negative references are required")

    print(f"Positive references: {len(POSITIVES)}")
    print(f"Negative references: {len(NEGATIVES)}")
    print(f"Independent test clips: {len(TEST_CLIPS)}")
    print("Loading CLAP model...")

    model = laion_clap.CLAP_Module(
        enable_fusion=False,
        device="cpu",
    )
    model.load_ckpt()

    embeddings = model.get_audio_embedding_from_filelist(
        x=[str(p) for p in files_to_check],
        use_tensor=False,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("CLAP returned a zero-length embedding")
    embeddings /= norms

    p_count = len(POSITIVES)
    n_count = len(NEGATIVES)

    positive_embeddings = embeddings[:p_count]
    negative_embeddings = embeddings[p_count:p_count + n_count]
    test_embeddings = embeddings[p_count + n_count:]

    rows = []

    for clip, embedding in zip(TEST_CLIPS, test_embeddings):
        p_scores = embedding @ positive_embeddings.T
        n_scores = embedding @ negative_embeddings.T

        p_idx = int(np.argmax(p_scores))
        n_idx = int(np.argmax(n_scores))

        positive_score = float(p_scores[p_idx])
        negative_score = float(n_scores[n_idx])
        margin = negative_score - positive_score

        rows.append({
            "test_clip": clip.name,
            "positive_similarity": round(positive_score, 4),
            "closest_positive_reference": POSITIVES[p_idx].name,
            "negative_similarity": round(negative_score, 4),
            "closest_negative_reference": NEGATIVES[n_idx].name,
            "negative_minus_positive": round(margin, 4),
            "closer_class": (
                "positive" if positive_score > negative_score
                else "negative" if negative_score > positive_score
                else "tie"
            ),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "external-test-scores.csv"

    with report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("\nExternal test results:")
    for row in rows:
        print(f'\n{row["test_clip"]}')
        print(
            f'  Positive similarity: '
            f'{row["positive_similarity"]:.4f} '
            f'({row["closest_positive_reference"]})'
        )
        print(
            f'  Negative similarity: '
            f'{row["negative_similarity"]:.4f} '
            f'({row["closest_negative_reference"]})'
        )
        print(
            f'  Margin (negative - positive): '
            f'{row["negative_minus_positive"]:+.4f}'
        )
        print(f'  Closer class: {row["closer_class"]}')

    print(f"\nCSV report saved to: {report}")

if __name__ == "__main__":
    main()
