import subprocess
import wave

import pytest

from app.audio_preprocessing import (
    AudioPreparationError,
    prepare_audio,
)


def make_wav(path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\x00" * 44100 * 4)


def test_converts_without_modifying_source(tmp_path):
    source = tmp_path / "original.wav"
    output = tmp_path / "analysis.wav"
    make_wav(source)
    original = source.read_bytes()

    result = prepare_audio(source, output)

    assert source.read_bytes() == original
    assert result["sample_rate"] == 16000
    assert result["channels"] == 1
    assert result["duration_seconds"] == pytest.approx(1, abs=0.01)
    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1


def test_missing_source(tmp_path):
    with pytest.raises(AudioPreparationError):
        prepare_audio(tmp_path / "missing.mp3", tmp_path / "out.wav")


def test_never_overwrites_existing_destination(tmp_path):
    source = tmp_path / "original.wav"
    output = tmp_path / "existing.wav"
    make_wav(source)
    output.write_bytes(b"protected")

    with pytest.raises(AudioPreparationError):
        prepare_audio(source, output)

    assert output.read_bytes() == b"protected"


def test_rejects_invalid_audio(tmp_path):
    source = tmp_path / "invalid.mp3"
    output = tmp_path / "analysis.wav"
    source.write_bytes(b"not an audio file")

    with pytest.raises(AudioPreparationError):
        prepare_audio(source, output)

    assert not output.exists()


def test_mp3_conversion(tmp_path):
    source_wav = tmp_path / "source.wav"
    source_mp3 = tmp_path / "source.mp3"
    output = tmp_path / "analysis.wav"
    make_wav(source_wav)

    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-i", str(source_wav), str(source_mp3),
        ],
        check=True, capture_output=True, timeout=30,
    )

    result = prepare_audio(source_mp3, output)

    assert output.is_file()
    assert result["sample_rate"] == 16000
    assert result["duration_seconds"] > 0


def test_failed_conversion_cleans_temporary_file(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    output = tmp_path / "analysis.wav"
    make_wav(source)

    original_run = subprocess.run

    def failing_run(args, **kwargs):
        if args[0] == "ffmpeg":
            raise subprocess.CalledProcessError(1, args)
        return original_run(args, **kwargs)

    monkeypatch.setattr(
        "app.audio_preprocessing.subprocess.run",
        failing_run,
    )

    with pytest.raises(AudioPreparationError):
        prepare_audio(source, output)

    assert not output.exists()
    assert list(tmp_path.glob(".crowdclean-*.wav")) == []


def test_existing_destination_preserved_after_conversion(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    output = tmp_path / "analysis.wav"
    make_wav(source)

    original_run = subprocess.run

    def racing_run(args, **kwargs):
        result = original_run(args, **kwargs)
        if args[0] == "ffmpeg":
            output.write_bytes(b"created concurrently")
        return result

    monkeypatch.setattr(
        "app.audio_preprocessing.subprocess.run",
        racing_run,
    )

    with pytest.raises(AudioPreparationError):
        prepare_audio(source, output)

    assert output.read_bytes() == b"created concurrently"
    assert list(tmp_path.glob(".crowdclean-*.wav")) == []
