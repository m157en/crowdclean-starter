from app.audio_pipeline import merge_intervals


def test_merge_overlapping_intervals():
    result = merge_intervals([
        {"start": 1.0, "end": 2.0},
        {"start": 1.9, "end": 3.0},
    ])
    assert result == [{"start": 1.0, "end": 3.0}]


def test_merge_nearby_intervals():
    result = merge_intervals([
        {"start": 1.0, "end": 2.0},
        {"start": 2.1, "end": 3.0},
    ])
    assert result == [{"start": 1.0, "end": 3.0}]


def test_keep_separate_intervals():
    result = merge_intervals([
        {"start": 1.0, "end": 2.0},
        {"start": 4.0, "end": 5.0},
    ])
    assert len(result) == 2


def test_analyze_wav_uses_review_candidate_threshold(tmp_path, monkeypatch):
    import wave
    import numpy as np
    from app import audio_pipeline

    wav_path = tmp_path / "short.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(np.zeros(16000, dtype="<i2").tobytes())

    seen = []

    monkeypatch.setattr(audio_pipeline, "load_silero_vad", lambda: object())

    def fake_get_speech_timestamps(audio, model, **kwargs):
        seen.append(kwargs["threshold"])
        return [{"start": 0.2, "end": 0.5}]

    monkeypatch.setattr(audio_pipeline, "get_speech_timestamps", fake_get_speech_timestamps)
    result = audio_pipeline.analyze_wav(wav_path)
    assert seen == [0.3]
    assert result["status"] == "pending_review"
    assert result["speech_intervals"] == [{"start": 0.2, "end": 0.5}]
