from pathlib import Path
import csv
import tempfile
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
import laion_clap

TEST_DIR = Path("storage/analysis/review/lost-frequencies")
OUT_DIR = Path("storage/analysis/reference-scan")

TEST_CLIPS = [
    TEST_DIR / "candidate-204.wav",
    TEST_DIR / "candidate-421.wav",
]

TARGET_SR = 16000
WINDOW_SEC = 1.0
STEP_SEC = 0.25

# Описания речи диджея — REMOVE
REMOVE_PROMPTS = [
    "A DJ speaking to the crowd over loud electronic dance music.",
    "A DJ shouting to hype up the audience at a live music festival.",
    "A spoken announcement by a DJ over a dance music track.",
]

# Описания обычной музыки — KEEP
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
    missing = [str(p) for p in TEST_CLIPS if not p.is_file()]
    if missing:
        raise FileNotFoundError("\n".join(missing))

    window_samples = int(WINDOW_SEC * TARGET_SR)
    step_samples = int(STEP_SEC * TARGET_SR)
    window_info = []

    with tempfile.TemporaryDirectory(prefix="crowdclean-text-") as tmp:
        tmp_dir = Path(tmp)
        window_files = []

        for clip in TEST_CLIPS:
            audio = load_mono_16k(clip)

            for index, start in enumerate(
                range(0, len(audio) - window_samples + 1, step_samples)
            ):
                end = start + window_samples
                path = tmp_dir / f"{clip.stem}_{index:03d}.wav"
                sf.write(path, audio[start:end], TARGET_SR, subtype="PCM_16")
                window_files.append(path)

                window_info.append({
                    "test_clip": clip.name,
                    "window_start_sec": round(start / TARGET_SR, 2),
                    "window_end_sec": round(end / TARGET_SR, 2),
                })

        print(f"Test windows: {len(window_files)}")
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
                "closer_class": (
                    "remove" if margin > 0
                    else "keep" if margin < 0
                    else "tie"
                ),
            })

        report = OUT_DIR / "external-test-text-scores.csv"
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        fields = [
            "test_clip",
            "window_start_sec",
            "window_end_sec",
            "text_keep_similarity",
            "text_remove_similarity",
            "remove_minus_keep",
            "closer_class",
        ]

        with report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        print("\nText-prompt results:")
        for row in rows:
            print(
                f'{row["test_clip"]:24} '
                f'{row["window_start_sec"]:5.2f}-'
                f'{row["window_end_sec"]:5.2f}s | '
                f'KEEP={row["text_keep_similarity"]:.4f} '
                f'REMOVE={row["text_remove_similarity"]:.4f} '
                f'MARGIN={row["remove_minus_keep"]:+.4f} | '
                f'{row["closer_class"]}'
            )

        print(f"\nCSV report saved to: {report}")


if __name__ == "__main__":
    main()
