"""API integration tests for explicit, review-only audio analysis."""

from pathlib import Path

from app import audio_pipeline, audio_preprocessing


def _upload(client):
    response = client.post(
        "/api/v1/jobs/upload",
        files={"file": ("mix.wav", b"fake audio payload", "audio/wav")},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_analyze_upload_persists_pending_segments(client, monkeypatch):
    job_id = _upload(client)

    def fake_prepare(source, destination):
        assert Path(source).is_file()
        Path(destination).write_bytes(b"prepared")
        return {"duration_seconds": 12.0}

    def fake_analyze(path):
        assert Path(path).is_file()
        return {"speech_intervals": [
            {"start": 2.0, "end": 3.0},
            {"start": 7.0, "end": 8.0},
        ]}

    monkeypatch.setattr(audio_preprocessing, "prepare_audio", fake_prepare)
    monkeypatch.setattr(audio_pipeline, "analyze_wav", fake_analyze)

    response = client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["duration_seconds"] == 12.0

    segments = client.get(f"/api/v1/jobs/{job_id}/segments").json()
    assert len(segments) == 2
    assert [segment["decision"] for segment in segments] == ["pending", "pending"]

    updated = client.patch(
        f"/api/v1/segments/{segments[0]['id']}",
        json={"decision": "remove"},
    )
    assert updated.status_code == 200
    assert updated.json()["decision"] == "remove"
    assert client.get(f"/api/v1/jobs/{job_id}/segments").json()[1]["decision"] == "pending"

    repeated = client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert repeated.status_code == 409
    assert len(client.get(f"/api/v1/jobs/{job_id}/segments").json()) == 2


def test_analyze_failure_sets_failed_without_segments(client, monkeypatch):
    job_id = _upload(client)

    def broken_prepare(source, destination):
        raise RuntimeError("bad audio")

    monkeypatch.setattr(audio_preprocessing, "prepare_audio", broken_prepare)
    response = client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert "bad audio" in response.json()["error_message"]
    assert client.get(f"/api/v1/jobs/{job_id}/segments").json() == []


def test_analyze_rejects_url_job(client):
    response = client.post(
        "/api/v1/jobs/url",
        json={"source_url": "https://example.org/mix.mp3"},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    response = client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert response.status_code == 409


def test_analyze_missing_job(client):
    response = client.post("/api/v1/jobs/does-not-exist/analyze")
    assert response.status_code == 404


def test_analyze_rejects_invalid_intervals(client, monkeypatch):
    job_id = _upload(client)

    def fake_prepare(source, destination):
        Path(destination).write_bytes(b"prepared")
        return {"duration_seconds": 5.0}

    monkeypatch.setattr(audio_preprocessing, "prepare_audio", fake_prepare)
    monkeypatch.setattr(
        audio_pipeline, "analyze_wav",
        lambda path: {"speech_intervals": [{"start": 4.0, "end": 3.0}]},
    )
    response = client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert client.get(f"/api/v1/jobs/{job_id}/segments").json() == []
