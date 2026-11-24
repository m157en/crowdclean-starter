import numpy as np
import pytest

from app.audio_stems_v4 import adaptive_mix, apply_residual, PROFILES


def stems():
    sr = 8000
    t = np.arange(sr * 3) / sr
    voice = np.column_stack([0.1*np.sin(2*np.pi*600*t)]*2).astype("float32")
    bed = np.column_stack([0.3*np.sin(2*np.pi*100*t)]*2).astype("float32")
    voice[:sr] *= 0.01
    bed[:sr] += voice[:sr] * 10
    residuals = np.stack([voice*0.8, voice*0.3, voice*0.5])
    return sr, voice, bed, residuals


def test_adaptive_weights_and_strength():
    sr, v, b, r = stems()
    outputs = []
    for profile in PROFILES:
        out, info = adaptive_mix(v, b, r, sr, profile)
        assert out.shape == v.shape
        assert np.isfinite(out).all()
        assert sum(info["mean_weights"]) == pytest.approx(1)
        assert min(info["weight_min"]) > 0
        assert info["residual_gain_max"] > info["residual_gain_min"]
        outputs.append(np.sqrt(np.mean(out**2)))
    assert outputs[0] > outputs[1] > outputs[2]


def test_context_and_full_stem_control():
    sr, v, b, _ = stems()
    original = v + b
    out, clipped = apply_residual(original, v, np.zeros_like(v), sr, 1, 2)
    assert np.array_equal(out[:sr//2], original[:sr//2])
    assert np.array_equal(out[int(sr*2.5):], original[int(sr*2.5):])
    np.testing.assert_allclose(out[sr:2*sr], b[sr:2*sr], atol=1e-7)
    assert clipped == 0


def test_mismatched_and_nonfinite_rejected():
    sr, v, b, r = stems()
    with pytest.raises(ValueError):
        adaptive_mix(v[:-1], b, r, sr, "strong")
    r[0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        adaptive_mix(v, b, r, sr, "strong")


def test_local_peak_limit_does_not_change_context():
    sr, v, b, _ = stems()
    original = np.full_like(v, 0.9)
    out, clipped = apply_residual(original, v, v + 1, sr, 1, 2)
    assert clipped > 0
    assert np.max(out) <= 0.999001
    assert np.array_equal(out[:sr//2], original[:sr//2])
