import numpy as np
import pytest

from app.audio_stems import suppress_vocals, validate_target


def test_vocal_only_suppression_preserves_instrumental():
    rate = 100
    vocals = np.full((400, 2), 0.3, dtype=np.float32)
    instrumental = np.full((400, 2), 0.2, dtype=np.float32)
    mixed = suppress_vocals(vocals, instrumental, rate, 1.0, 2.0, gain=0.0, fade=0.1)
    assert np.allclose(mixed[150], 0.2)
    assert np.allclose(mixed[50], 0.5)
    assert np.allclose(mixed[250], 0.5)


def test_vocal_gain_one_preserves_stem_sum():
    vocal = np.full((200, 2), 0.1, dtype=np.float32)
    instrumental = np.full((200, 2), -0.2, dtype=np.float32)
    mixed = suppress_vocals(vocal, instrumental, 100, 0.5, 1.5, gain=1.0)
    assert np.allclose(mixed, vocal + instrumental)


def test_validate_boundary_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate_target({"start": 20, "end": 25, "precise_boundary": {"start": 19, "end": 21}})
    assert validate_target({"start": 20, "end": 25,
                            "precise_boundary": {"start": 21, "end": 23}}) == (21, 23, 19, 25)


def test_rejects_misaligned_stems():
    with pytest.raises(ValueError):
        suppress_vocals(np.zeros((100, 2)), np.zeros((99, 2)), 100, 0.2, 0.6)
