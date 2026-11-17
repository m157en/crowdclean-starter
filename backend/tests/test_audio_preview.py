import json
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from app.audio_preview import create_previews, duck_pcm, gain_at


def test_gain_envelope_is_smooth_and_bounded():
    assert gain_at(0, 2, 4) == 1
    assert gain_at(2, 2, 4) == 0.25
    assert gain_at(3, 2, 4) == 0.25
    assert gain_at(4.25, 2, 4) == 1
    assert 0.25 < gain_at(1.875, 2, 4) < 1


def test_pcm_ducking_keeps_length_and_original_bytes():
    raw = (1000).to_bytes(2, "little", signed=True) * 160
    result = duck_pcm(raw, 16000, 0, 0.005, gain=0.25)
    assert len(result) == len(raw)
    assert raw != result
    assert raw[:2] == (1000).to_bytes(2, "little", signed=True)


def test_preview_creates_ab_files_without_overwriting(tmp_path):
    source = tmp_path / "mix.mp3"
    source.write_bytes(b"unchanged source")
    dataset = tmp_path / "labels.json"
    dataset.write_text(json.dumps({"items": [
        {"file": "review-006.wav", "start": 1.0, "end": 6.0,
         "decision": "remove", "precise_boundary": {"start": 2.0, "end": 4.0}},
        {"file": "review-007.wav", "start": 7.0, "end": 9.0, "decision": "keep"}
    ]}))
    output = tmp_path / "preview"
    pcm = (1000).to_bytes(2, "little", signed=True) * 16000 * 6
    with patch("app.audio_preview.subprocess.run") as run:
        run.return_value.stdout = pcm
        report = create_previews(source, dataset, output)
    assert len(report) == 1
    assert source.read_bytes() == b"unchanged source"
    with wave.open(str(output / "review-006-original.wav"), "rb") as audio:
        assert audio.getnframes() == 96000
    with wave.open(str(output / "review-006-ducked.wav"), "rb") as audio:
        assert audio.getnframes() == 96000
    assert (output / "report.json").is_file()
    with pytest.raises(FileExistsError):
        create_previews(source, dataset, output)
