"""V4 experimental adaptive residual mixing; never a DJ-identity classifier."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from app.audio_stems_v3 import TARGETS, envelope, band_voice, spectral_repair
from app.audio_metrics import evaluate
from app.audio_review_static import export_review

# Prior weights for selective, partial, spectral; retention range of residual.
PROFILES = {
    "balanced": ((0.45, 0.20, 0.35), 0.55, 0.85, 0.5),
    "strong": ((0.25, 0.40, 0.35), 0.20, 0.50, 1.0),
    "maximum": ((0.15, 0.50, 0.35), 0.03, 0.20, 1.6),
}


def rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def speech_band(x, sr):
    sos = butter(4, [180, min(4500, sr * 0.45)], btype="bandpass",
                 fs=sr, output="sos")
    return sosfiltfilt(sos, x, axis=0)


def adaptive_mix(voice, bed, residuals, sr, profile):
    """Mix three phase-aligned residuals, with shared stereo weights.

    Costs use speech-band energy, not verified DJ identity. The residual
    attenuation increases where vocal-band energy dominates accompaniment.
    Smooth interpolation avoids hard block transitions.
    """
    voice, bed, residuals = map(np.asarray, (voice, bed, residuals))
    if (voice.ndim != 2 or voice.shape != bed.shape
            or residuals.shape != (3, *voice.shape)
            or sr < 2000 or len(voice) < 128
            or not all(np.isfinite(x).all() for x in (voice, bed, residuals))):
        raise ValueError("Invalid aligned stems")
    prior, low, high, strength = PROFILES[profile]
    vb = speech_band(voice, sr)
    bb = speech_band(bed, sr)
    rb = np.stack([speech_band(x, sr) for x in residuals])
    block = max(1, round(sr * 0.25))
    centers, weights, gains = [], [], []
    for i in range(0, len(voice), block):
        j = min(i + block, len(voice))
        v = rms(vb[i:j])
        b = rms(bb[i:j])
        prominence = v / (v + b + 1e-8)
        cost = np.array([rms(x[i:j]) / (v + 1e-8) for x in rb])
        cost = np.clip(cost, 0, 5)
        # The prior prevents collapse to one method, even in quiet regions.
        w = np.asarray(prior) * np.exp(-strength * cost)
        w /= w.sum()
        w = 0.85 * w + 0.15 * np.asarray(prior)
        centers.append((i + j - 1) / 2)
        weights.append(w)
        gains.append(high - (high - low) * prominence)
    t = np.arange(len(voice))
    w = np.column_stack([np.interp(t, centers, np.asarray(weights)[:, k])
                         for k in range(3)])
    gain = np.interp(t, centers, gains)
    mixed = np.sum(residuals * w.T[:, :, None], axis=0) * gain[:, None]
    evidence = {"mean_weights": w.mean(axis=0).tolist(),
                "weight_min": w.min(axis=0).tolist(),
                "weight_max": w.max(axis=0).tolist(),
                "residual_gain_min": float(gain.min()),
                "residual_gain_max": float(gain.max())}
    return mixed.astype(np.float32), evidence


def apply_residual(original, voice, residual, sr, a, b):
    """Subtract only the estimated removed signal from the original mixture."""
    if original.shape != voice.shape or voice.shape != residual.shape:
        raise ValueError("Unaligned audio")
    if not all(np.isfinite(x).all() for x in (original, voice, residual)):
        raise ValueError("Non-finite audio")
    e = envelope(len(original), sr, a, b)
    candidate = original + e * (residual - voice)
    # Bound edited samples without altering context or globally normalizing.
    edited = e[:, 0] > 0
    clipped = int(np.count_nonzero(np.abs(candidate[edited]) > 0.999))
    candidate[edited] = np.clip(candidate[edited], -0.999, 0.999)
    return candidate.astype(np.float32), clipped


def create(source, output):
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crowdclean-v4-", dir=output.parent) as tmp:
        root = Path(tmp)
        result = root / "results"
        result.mkdir()
        items = []
        for episode, (start, end) in TARGETS.items():
            window_start = start - 3
            decoded = root / f"{episode}.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-ss", str(window_start), "-i", str(source), "-t",
                            str(end - start + 6), "-ar", "44100", "-ac", "2",
                            "-c:a", "pcm_f32le", str(decoded)], check=True)
            subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals",
                            "-n", "htdemucs", "-o", str(root / "separated"),
                            str(decoded)], check=True)
            stems = root / "separated" / "htdemucs" / episode
            original, sr = sf.read(decoded, dtype="float32", always_2d=True)
            voice, vr = sf.read(stems / "vocals.wav", dtype="float32", always_2d=True)
            bed, br = sf.read(stems / "no_vocals.wav", dtype="float32", always_2d=True)
            if sr != vr or sr != br or sr != 44100 or original.shape != voice.shape or voice.shape != bed.shape:
                raise ValueError("Unaligned source and stems")
            a, b = start - window_start, end - window_start
            if not all(np.isfinite(x).all() for x in (original, voice, bed)):
                raise ValueError("Non-finite source or stems")
            residuals = np.stack([band_voice(voice, sr), 0.30 * voice,
                                  spectral_repair(voice, sr, a, b)])
            original_name = f"{episode}-original-v4.wav"
            # Use the same PCM preview range for reference and processed context.
            source_over = int(np.count_nonzero(np.abs(original) > 0.999))
            original = np.clip(original, -0.999, 0.999)
            sf.write(result / original_name, original, sr, subtype="PCM_16")
            for method in (*PROFILES, "stem-only-control"):
                if method == "stem-only-control":
                    residual, evidence = np.zeros_like(voice), {"control": True}
                else:
                    residual, evidence = adaptive_mix(voice, bed, residuals, sr, method)
                candidate, clipped = apply_residual(original, voice, residual, sr, a, b)
                name = f"{episode}-{method}-v4.wav"
                sf.write(result / name, candidate, sr, subtype="PCM_16")
                target = slice(round(a * sr), round(b * sr))
                # Proxy only: not actual voice suppression in the final mix.
                stem_ratio = 20 * np.log10(max(rms(residual[target]), 1e-10)
                                            / max(rms(voice[target]), 1e-10))
                items.append({"episode": f"{episode}-{method}", "source_episode": episode,
                              "start": start, "end": end, "window_start": window_start,
                              "original": original_name, "preview": name, "method": method,
                              "clipped_samples_prevented": clipped,
                              "source_preview_limited_samples": source_over,
                              "estimated_stem_residual_db": round(float(stem_ratio), 2),
                              **evidence})
        (result / "report.json").write_text(json.dumps({
            "source": source.name, "items": items,
            "warning": "Estimated vocal stem includes musical vocals and leakage. Listening required."
        }, indent=2) + "\n")
        (result / "metrics.json").write_text(json.dumps(evaluate(result), indent=2) + "\n")
        export_review(result, version="v4")
        if output.exists():
            raise FileExistsError(output)
        result.rename(output)
    return items


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    items = create(args.source, args.output)
    print(json.dumps({"status": "V4_READY_FOR_LISTENING", "variants": len(items),
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
