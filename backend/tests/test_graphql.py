def test_graphql_service_status(client):
    response = client.post("/graphql", json={"query": "{ serviceStatus }"})

    assert response.status_code == 200
    assert response.json() == {"data": {"serviceStatus": "ok"}}


def test_graphql_can_read_job_created_via_rest(client):
    created = client.post("/api/v1/jobs/url", json={"source_url": "https://example.com/set.mp3"}).json()
    query = "query GetJob($id: String!) { job(id: $id) { id status sourceType sourceUrl } }"

    response = client.post("/graphql", json={"query": query, "variables": {"id": created["id"]}})

    assert response.status_code == 200
    job = response.json()["data"]["job"]
    assert job["id"] == created["id"]
    assert job["status"] == "queued"
    assert job["sourceType"] == "url"


def test_graphql_update_segment_decision(client, db_session):
    from app.models import AudioJob, AudioSegment

    job = AudioJob(source_type="url", source_url="https://example.com/set.mp3", status="review")
    db_session.add(job)
    db_session.flush()
    segment = AudioSegment(job_id=job.id, start_seconds=20.0, end_seconds=23.5, confidence=0.8)
    db_session.add(segment)
    db_session.commit()
    segment_id = segment.id

    query = "mutation Update($id: Int!, $decision: String!) { updateSegmentDecision(segmentId: $id, decision: $decision) { id decision } }"
    response = client.post("/graphql", json={"query": query, "variables": {"id": segment_id, "decision": "keep"}})

    assert response.status_code == 200
    assert response.json()["data"]["updateSegmentDecision"]["decision"] == "keep"

def test_graphql_jobs_returns_created_job(client):
    created = client.post(
        "/api/v1/jobs/url",
        json={"source_url": "https://example.com/set.mp3"},
    ).json()

    response = client.post(
        "/graphql",
        json={"query": "{ jobs { id status sourceType } }"},
    )

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    assert any(job["id"] == created["id"] for job in jobs)


def test_graphql_unknown_job_returns_null(client):
    response = client.post(
        "/graphql",
        json={
            "query": '{ job(id: "unknown-job") { id status } }'
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["job"] is None


def test_graphql_segments_are_sorted(client, db_session):
    from app.models import AudioJob, AudioSegment

    job = AudioJob(
        source_type="url",
        source_url="https://example.com/set.mp3",
        status="review",
    )
    db_session.add(job)
    db_session.flush()

    db_session.add_all([
        AudioSegment(
            job_id=job.id,
            start_seconds=20.0,
            end_seconds=23.0,
            confidence=0.8,
        ),
        AudioSegment(
            job_id=job.id,
            start_seconds=5.0,
            end_seconds=7.0,
            confidence=0.9,
        ),
    ])
    db_session.commit()

    response = client.post(
        "/graphql",
        json={
            "query": """
                query GetSegments($jobId: String!) {
                    segments(jobId: $jobId) {
                        startSeconds
                        endSeconds
                    }
                }
            """,
            "variables": {"jobId": job.id},
        },
    )

    assert response.status_code == 200
    segments = response.json()["data"]["segments"]
    assert [s["startSeconds"] for s in segments] == [5.0, 20.0]


def test_graphql_unknown_segment_returns_null(client):
    response = client.post(
        "/graphql",
        json={
            "query": """
                mutation {
                    updateSegmentDecision(
                        segmentId: 999999,
                        decision: "remove"
                    ) {
                        id
                        decision
                    }
                }
            """
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["updateSegmentDecision"] is None


def test_graphql_rejects_invalid_decision(client):
    response = client.post(
        "/graphql",
        json={
            "query": """
                mutation {
                    updateSegmentDecision(
                        segmentId: 999999,
                        decision: "delete"
                    ) {
                        id
                        decision
                    }
                }
            """
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "errors" in body
    assert any(
        "decision must be one of" in error["message"]
        for error in body["errors"]
    )
