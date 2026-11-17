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
