import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app import ab_review


def sample_report(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps({"items": [
        {"episode": "review-006", "start": 1.0, "end": 2.0,
         "original": "review-006-original.wav", "preview": "review-006-ducked.wav"}
    ]}), encoding="utf-8")
    (folder / "review-006-original.wav").write_bytes(b"wav")
    (folder / "review-006-ducked.wav").write_bytes(b"wav")


def test_ab_items_and_rating_roundtrip(tmp_path):
    sample_report(tmp_path)
    with patch.object(ab_review, "preview_dir", return_value=tmp_path):
        assert ab_review.items()["items"][0]["rating"] is None
        assert ab_review.rate("review-006", ab_review.Rating(verdict="worse"))["rating"] == "worse"
        assert ab_review.items()["items"][0]["rating"] == "worse"
        assert json.loads((tmp_path / "ratings.json").read_text()) == {"review-006": "worse"}


def test_ab_rejects_unknown_episode_and_audio(tmp_path):
    sample_report(tmp_path)
    with patch.object(ab_review, "preview_dir", return_value=tmp_path):
        with pytest.raises(HTTPException) as episode:
            ab_review.rate("not-listed", ab_review.Rating(verdict="better"))
        assert episode.value.status_code == 404
        with pytest.raises(HTTPException) as audio:
            ab_review.audio("../other.wav")
        assert audio.value.status_code == 404


def test_ab_page_uses_local_report(tmp_path):
    sample_report(tmp_path)
    with patch.object(ab_review, "preview_dir", return_value=tmp_path):
        assert "A/B-прослушивание" in ab_review.page().body.decode("utf-8")


def test_v3_route_and_audio_list_use_own_preview_folder(client, tmp_path, monkeypatch):
    folder = tmp_path / "analysis" / "ab-stems-v3"
    sample_report(folder)
    monkeypatch.setattr(ab_review.settings, "storage_dir", tmp_path)
    monkeypatch.setattr(ab_review.settings, "environment", "local")
    page_response = client.get("/ab/stems-v3")
    assert page_response.status_code == 200
    assert "/ab/stems-v3/items" in page_response.text
    assert "/ab/stems-v3/audio/" in page_response.text
    response = client.get("/ab/stems-v3/items")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert client.get("/ab/stems-v3/audio/review-006-original.wav").status_code == 200
    assert client.get("/ab/stems-v3/audio/nonexistent.wav").status_code == 404
