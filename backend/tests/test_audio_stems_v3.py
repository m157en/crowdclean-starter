"""Fast checks for experimental v3 signal processing; no model download."""
import numpy as np

from app.audio_stems_v3 import TARGETS, METHODS, envelope, band_voice, spectral_repair


def test_six_distinct_candidates():
    assert len(TARGETS) * len(METHODS) == 6
    assert TARGETS["review-013"][0] == 2346.0


def test_envelope_preserves_outside_and_crossfades():
    e = envelope(1000, 100, 3.0, 6.0)
    assert e.shape == (1000, 1)
    assert e[0, 0] == 0
    assert e[400, 0] == 1
    assert e[900, 0] == 0
    assert 0 < e[285, 0] < 1


def test_spectral_methods_finite_and_aligned():
    sr = 8000
    t = np.arange(sr) / sr
    signal = np.column_stack([np.sin(2*np.pi*500*t), np.sin(2*np.pi*700*t)]).astype("float32")
    for fn in (lambda x: band_voice(x, sr),
               lambda x: spectral_repair(x, sr, 0.3, 0.6)):
        out = fn(signal)
        assert out.shape == signal.shape
        assert np.isfinite(out).all()
