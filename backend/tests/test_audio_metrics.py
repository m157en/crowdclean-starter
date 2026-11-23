import json

import numpy as np
import soundfile as sf
import pytest

from app.audio_metrics import analyze_pair


def test_metrics_detect_target_attenuation_without_context_damage():
    rate = 100
    original = np.ones((600, 2), dtype=np.float32) * 0.5
    processed = original.copy()
    processed[200:300] *= 0.25
    result = analyze_pair(original, processed, rate, 2, 3)
    assert result["target_level_change_db"] == pytest.approx(-12.04, abs=0.03)
    assert result["context_rms_error"] == 0
    assert result["clipped_samples"] == 0


def test_metrics_detect_collateral_damage():
    original = np.ones((600, 2), dtype=np.float32) * 0.5
    processed = original * 0.5
    result = analyze_pair(original, processed, 100, 2, 3)
    assert result["context_rms_error"] > 0.2


def test_metrics_reject_misalignment():
    with pytest.raises(ValueError):
        analyze_pair(np.ones((600, 2)), np.ones((599, 2)), 100, 2, 3)


def test_report_window_start_and_corrected_onset_take_precedence(tmp_path):
    rate = 100
    original = np.full((600, 2), 0.5, dtype=np.float32)
    processed = original.copy()
    processed[100:300] *= 0.5
    sf.write(tmp_path / "original.wav", original, rate)
    sf.write(tmp_path / "preview.wav", processed, rate)
    (tmp_path / "report.json").write_text(json.dumps({"items": [{
        "episode": "review-013-partial",
        "source_episode": "review-013",
        "start": 101.0,
        "end": 103.0,
        "window_start": 100.0,
        "original": "original.wav",
        "preview": "preview.wav",
        "method": "partial"
    }]}), encoding="utf-8")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"items": [{
        "file": "review-013.wav",
        "precise_boundary": {"start": 102.5, "end": 103.0}
    }]}), encoding="utf-8")
    from app.audio_metrics import evaluate
    result = evaluate(tmp_path, source_dataset=dataset)
    assert result["evaluated"] == 1
    assert result["items"][0]["target_level_change_db"] == pytest.approx(-6.02, abs=0.04)
    assert result["items"][0]["context_rms_error"] == 0
