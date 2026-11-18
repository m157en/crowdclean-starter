import numpy as np
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
