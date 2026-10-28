from app.models import AudioJob


def test_create_url_job_returns_202_and_queued_status(client):
    response = client.post("/api/v1/jobs/url", json={"source_url": "https://example.com/dj-set.mp3"})

    assert response.status_code == 202
    body = response.json()
    assert body["source_type"] == "url"
    assert body["source_url"] == "https://example.com/dj-set.mp3"
    assert body["status"] == "queued"
    assert body["id"]


def test_create_url_job_rejects_non_http_url(client):
    response = client.post("/api/v1/jobs/url", json={"source_url": "file:///etc/passwd"})

    assert response.status_code == 422


def test_get_unknown_job_returns_404(client):
    response = client.get("/api/v1/jobs/not-a-real-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Audio job not found"


def test_list_jobs_supports_pagination(client):
    for index in range(3):
        client.post("/api/v1/jobs/url", json={"source_url": f"https://example.com/set-{index}.mp3"})

    response = client.get("/api/v1/jobs?limit=2&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert len(body["items"]) == 2


def test_upload_creates_job_and_persists_file(client):
    response = client.post(
        "/api/v1/jobs/upload",
        files={"file": ("festival-set.mp3", b"fake-audio-content", "audio/mpeg")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["source_type"] == "upload"
    assert body["original_filename"] == "festival-set.mp3"


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/v1/jobs/upload",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 415
    assert "Unsupported audio extension" in response.json()["detail"]


def test_segment_decision_can_be_updated(client, db_session):
    job = AudioJob(source_type="url", source_url="https://example.com/set.mp3", status="review")
    db_session.add(job)
    db_session.flush()
    from app.models import AudioSegment

    segment = AudioSegment(job_id=job.id, start_seconds=12.0, end_seconds=15.0, confidence=0.92)
    db_session.add(segment)
    db_session.commit()
    segment_id = segment.id

    response = client.patch(f"/api/v1/segments/{segment_id}", json={"decision": "remove"})

    assert response.status_code == 200
    assert response.json()["decision"] == "remove"


def test_segment_decision_rejects_unknown_value(client):
    response = client.patch("/api/v1/segments/123", json={"decision": "maybe"})

    assert response.status_code == 422

def test_get_existing_job_returns_200(client, db_session):
    job = AudioJob(
        source_type="url",
        source_url="https://example.com/set.mp3",
        status="review",
    )
    db_session.add(job)
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["id"] == job.id
    assert response.json()["status"] == "review"


def test_list_segments_returns_sorted_segments(client, db_session):
    from app.models import AudioSegment

    job = AudioJob(
        source_type="url",
        source_url="https://example.com/set.mp3",
    )
    db_session.add(job)
    db_session.flush()

    db_session.add_all([
        AudioSegment(
            job_id=job.id,
            start_seconds=15.0,
            end_seconds=17.0,
            confidence=0.8,
        ),
        AudioSegment(
            job_id=job.id,
            start_seconds=5.0,
            end_seconds=6.0,
            confidence=0.9,
        ),
    ])
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{job.id}/segments")

    assert response.status_code == 200
    segments = response.json()
    assert len(segments) == 2
    assert [s["start_seconds"] for s in segments] == [5.0, 15.0]


def test_list_segments_for_unknown_job_returns_404(client):
    response = client.get("/api/v1/jobs/unknown-job/segments")

    assert response.status_code == 404
    assert response.json()["detail"] == "Audio job not found"


def test_update_unknown_segment_returns_404(client):
    response = client.patch(
        "/api/v1/segments/999999",
        json={"decision": "remove"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Audio segment not found"
