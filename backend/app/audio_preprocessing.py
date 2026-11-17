"""Safe audio preparation for speech detection."""

import json
import math
import subprocess
import tempfile
import os
from pathlib import Path


class AudioPreparationError(ValueError):
    pass


def prepare_audio(source: str | Path, destination: str | Path) -> dict:
    """Convert supported audio to mono 16 kHz PCM WAV.

    Never modify the original input. The destination must not exist.
    """
    source = Path(source).resolve()
    destination = Path(destination).resolve()

    if not source.is_file():
        raise AudioPreparationError("Source audio file not found")
    if destination.exists():
        raise AudioPreparationError("Destination already exists")
    if source == destination:
        raise AudioPreparationError("Source and destination must differ")

    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=".crowdclean-",
        suffix=".wav",
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)

    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "json", str(source),
            ],
            capture_output=True, text=True, timeout=30,
            check=True,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        if not streams or streams[0].get("codec_type") != "audio":
            raise AudioPreparationError("No audio stream found")

        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-hide_banner",
                "-loglevel", "error", "-nostats",
                "-y", "-i", str(source),
                "-map", "0:a:0", "-vn",
                "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(temporary),
            ],
            capture_output=True, text=True,
            timeout=3600, check=True,
        )

        info = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", str(temporary),
            ],
            capture_output=True, text=True,
            timeout=30, check=True,
        )
        duration = float(json.loads(info.stdout)["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise AudioPreparationError("Invalid audio duration")

        os.link(temporary, destination)
        return {
            "source": str(source),
            "analysis_path": str(destination),
            "sample_rate": 16000,
            "channels": 1,
            "duration_seconds": round(duration, 3),
        }
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        raise AudioPreparationError("Audio conversion failed") from exc
    except AudioPreparationError:
        raise
    finally:
        temporary.unlink(missing_ok=True)
