"""CrowdClean v3 controlled, non-destructive three-method audio pilot.

Uses the same two annotated examples. Every output is a hypothesis, not validated
DJ removal. No changes to original source, previous previews, or annotations.
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import stft, istft

TARGETS = {"review-006": (1398.3, 1402.3),
           "review-013": (2346.0, 2354.0)}
METHODS = ("selective", "partial", "spectral")


def envelope(n, sr, a, b, fade=0.3):
    t = np.arange(n, dtype=np.float64) / sr
    e = np.zeros(n, dtype=np.float32)
    e[(t >= a) & (t <= b)] = 1
    left = (t > a-fade) & (t < a)
    right = (t > b) & (t < b+fade)
    e[left] = 0.5-0.5*np.cos(np.pi*(t[left]-(a-fade))/fade)
    e[right] = 0.5+0.5*np.cos(np.pi*(t[right]-b)/fade)
    return e[:, None]


def band_voice(vocals, sr):
    """Retain vocal-stem content outside broad speech band (not speaker ID)."""
    channels = []
    for ch in range(vocals.shape[1]):
        freqs, _, spec = stft(vocals[:, ch], fs=sr, nperseg=2048,
                              noverlap=1536, boundary="zeros")
        # Smooth band stop on vocal stem; keep bass and high-frequency elements.
        low = np.clip((freqs-180)/180, 0, 1)
        high = np.clip((6000-freqs)/1800, 0, 1)
        band = low*high
        _, recovered = istft(spec*(1-0.9*band[:, None]), fs=sr,
                             nperseg=2048, noverlap=1536, boundary=True)
        channels.append(recovered[:len(vocals)])
    return np.column_stack(channels).astype(np.float32)


def spectral_repair(vocals, sr, a, b):
    """Experimental time-frequency interpolation across speech band.

    Long spans cannot be faithfully reconstructed; this is a diagnostic baseline.
    """
    channels = []
    for ch in range(vocals.shape[1]):
        f, t, z = stft(vocals[:, ch], fs=sr, nperseg=2048,
                        noverlap=1536, boundary="zeros")
        inside = (t >= a) & (t <= b)
        speech = (f >= 250) & (f <= 4500)
        before = np.where(t < a-0.3)[0]
        after = np.where(t > b+0.3)[0]
        if len(before) and len(after):
            # Suppress vocal-stem speech band while retaining low/high residuals.
            # A conservative spectral floor is estimated from nearby context.
            context = np.concatenate([before[-12:], after[:12]])
            floor = np.median(np.abs(z[:, context]), axis=1)
            mag = np.abs(z)
            phase = np.exp(1j*np.angle(z))
            target = np.minimum(mag, floor[:, None]*0.65)
            mask = speech[:, None] & inside[None, :]
            z = np.where(mask, target*phase, z)
        _, reconstructed = istft(z, fs=sr, nperseg=2048,
                                  noverlap=1536, boundary=True)
        channels.append(reconstructed[:len(vocals)])
    return np.column_stack(channels).astype(np.float32)


def create(source, output):
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crowdclean-v3-", dir=output.parent) as tmp:
        root = Path(tmp)
        result = root/"results"
        result.mkdir()
        items = []
        for episode, (start, end) in TARGETS.items():
            window_start, window_end = start-3, end+3
            decoded = root/f"{episode}.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel",
                            "error", "-ss", str(window_start), "-i", str(source),
                            "-t", str(window_end-window_start), "-ar", "44100",
                            "-ac", "2", "-c:a", "pcm_f32le", str(decoded)],
                           check=True)
            subprocess.run([sys.executable, "-m", "demucs", "--two-stems",
                            "vocals", "-n", "htdemucs", "-o", str(root/"separated"),
                            str(decoded)], check=True)
            stems = root/"separated"/"htdemucs"/episode
            voice, sr = sf.read(stems/"vocals.wav", dtype="float32", always_2d=True)
            bed, br = sf.read(stems/"no_vocals.wav", dtype="float32", always_2d=True)
            original, orig_rate = sf.read(decoded, dtype="float32", always_2d=True)
            if sr != br or sr != orig_rate or sr != 44100:
                raise ValueError("Unaligned sample rates")
            n = min(len(original), len(voice), len(bed))
            original, voice, bed = original[:n], voice[:n], bed[:n]
            e = envelope(n, sr, start-window_start, end-window_start)
            # Demucs reconstruction can differ from source. Crossfade against
            # the original outside the edited interval, without global gain.
            variants = {
                "selective": bed+band_voice(voice, sr),
                "partial": bed+0.30*voice,
                "spectral": bed+spectral_repair(voice, sr,
                                                start-window_start, end-window_start)
            }
            original_name = f"{episode}-original-v3.wav"
            sf.write(result/original_name, original, sr, subtype="PCM_16")
            for method, candidate in variants.items():
                candidate = original*(1-e)+candidate*e
                peak = float(np.max(np.abs(candidate)))
                if not math.isfinite(peak):
                    raise ValueError("Non-finite audio")
                # Never silently normalize: record clipping risk and limit output.
                name = f"{episode}-{method}-v3.wav"
                sf.write(result/name, np.clip(candidate, -0.999, 0.999),
                         sr, subtype="PCM_16")
                items.append({"episode": f"{episode}-{method}", "source_episode": episode,
                              "start": start, "end": end, "original": original_name,
                              "preview": name, "method": method,
                              "peak_before_clipping": round(peak, 5),
                              "clipped_samples_prevented": int(np.count_nonzero(np.abs(candidate)>0.999))})
        (result/"report.json").write_text(json.dumps({
            "source": source.name, "items": items,
            "warning": "Three experimental hypotheses; none isolates DJ identity. Human listening required."
        }, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        result.rename(output)
    return items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("storage/analysis/ab-stems-v3"))
    args = p.parse_args()
    items = create(args.source, args.output)
    print(json.dumps({"status":"V3_READY_FOR_LISTENING",
                      "variants":len(items), "output":str(args.output)}))


if __name__ == "__main__":
    main()
