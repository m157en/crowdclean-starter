"""CrowdClean v2: isolated A/B pilot with music-level compensation.

Only two preselected episodes. Never modifies the source or v1 output.
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


TARGETS = {
    "review-006": (1398.3, 1402.3),
    # Listener reported speech ~1s into previous original preview
    # (previous preview began at 2345.0). New provisional onset = 2346.0.
    "review-013": (2346.0, 2354.0),
}


def rms(x):
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def compensate(instrumental, original, rate, start, end, cap_db=5.0):
    """Gain-match separated music to original using short neighboring music context.

    This does not guarantee music preservation or eliminate vocal bleed.
    """
    if instrumental.shape != original.shape or instrumental.ndim != 2:
        raise ValueError("unaligned stems")
    n = len(original)
    a, b = int(start * rate), int(end * rate)
    if not (rate > 0 and 0 <= a < b <= n):
        raise ValueError("invalid target")
    # Estimate music gain from context outside speech, not from the voice interval.
    context = int(1.0 * rate)
    indices = np.r_[max(0, a-context):a, b:min(n, b+context)]
    if len(indices) < int(rate * 0.25):
        raise ValueError("insufficient clean context for gain estimation")
    base = rms(instrumental[indices])
    reference = rms(original[indices])
    if base < 1e-5:
        raise ValueError("instrumental stem nearly silent")
    gain = min(reference / base, 10 ** (cap_db / 20))
    # Smooth transition from original outside target to boosted instrumental inside.
    fade = max(1, int(rate * 0.35))
    envelope = np.zeros(n, dtype=np.float32)
    envelope[a:b] = 1
    for i in range(max(0, a-fade), a):
        t = (i-(a-fade))/fade
        envelope[i] = 0.5 - 0.5 * math.cos(math.pi * t)
    for i in range(b, min(n, b+fade)):
        t = (i-b)/fade
        envelope[i] = 0.5 + 0.5 * math.cos(math.pi * t)
    output = original * (1-envelope[:, None]) + instrumental * gain * envelope[:, None]
    peak = float(np.max(np.abs(output)))
    # Avoid clipping without normalizing the whole audio: limit gain only if needed.
    if peak > 0.999:
        safe_gain = min(gain, gain * (0.999 / peak))
        output = original * (1-envelope[:, None]) + instrumental * safe_gain * envelope[:, None]
        gain = safe_gain
        peak = float(np.max(np.abs(output)))
    return np.clip(output, -0.999, 0.999), gain, peak


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("storage/samples/lost-frequencies.mp3"))
    parser.add_argument("--output", type=Path, default=Path("storage/analysis/ab-stems-v2"))
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("source missing")
    if args.output.exists():
        parser.error("output exists; previous results preserved")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crowdclean-v2-", dir=args.output.parent) as tmp:
        root = Path(tmp)
        out = root / "result"
        out.mkdir()
        report = []
        for episode, (start, end) in TARGETS.items():
            # 3 seconds of pre-roll to expose the beginning of speech in review-013.
            window_start, window_end = max(0, start-3), end+3
            decoded = root / (episode + ".wav")
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-ss", str(window_start), "-i", str(args.source),
                            "-t", str(window_end-window_start), "-ar", "44100", "-ac", "2",
                            "-c:a", "pcm_f32le", str(decoded)], check=True)
            separated = root / "separated"
            subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals",
                            "-n", "htdemucs", "-o", str(separated), str(decoded)], check=True)
            instrumental, rate = sf.read(separated/"htdemucs"/episode/"no_vocals.wav",
                                         dtype="float32", always_2d=True)
            original, original_rate = sf.read(decoded, dtype="float32", always_2d=True)
            if rate != original_rate or rate != 44100:
                raise ValueError("unexpected sample rate")
            n = min(len(original), len(instrumental))
            original, instrumental = original[:n], instrumental[:n]
            processed, gain, peak = compensate(instrumental, original, rate,
                                                 start-window_start, end-window_start)
            original_name = episode+"-original.wav"
            preview_name = episode+"-stems-v2.wav"
            sf.write(out/original_name, original, rate, subtype="PCM_16")
            sf.write(out/preview_name, processed, rate, subtype="PCM_16")
            report.append({"episode": episode, "start": start, "end": end,
                           "original": original_name, "preview": preview_name,
                           "method": "demucs_music_compensation_v2",
                           "music_gain_db": round(20*math.log10(gain), 2),
                           "peak_before_output_clip": round(peak, 5),
                           "window_start": window_start})
        (out/"report.json").write_text(json.dumps({
            "source": args.source.name,
            "warning": "Experimental: instrumental may retain voice or lose musical elements. Requires listening.",
            "items": report}, ensure_ascii=False, indent=2)+"\n")
        out.rename(args.output)
    print(json.dumps({"status":"V2_READY_FOR_LISTENING", "output":str(args.output),
                      "episodes":len(report)}))


if __name__ == "__main__":
    main()
