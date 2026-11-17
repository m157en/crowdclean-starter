import json
from pathlib import Path


def test_review_workflow(client, tmp_path):
    directory = Path(tmp_path) / "analysis/review/threshold-03"
    directory.mkdir(parents=True)
    audio = directory / "review-001.wav"
    audio.write_bytes(b"RIFFfake")
    manifest = [{"file": audio.name, "start": 1.0, "end": 4.0,
                 "detected_intervals": 2, "decision": "pending"}]
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert client.get("/review").status_code == 200
    assert client.get("/review/items").json() == manifest
    response = client.get("/review/audio/review-001.wav")
    assert response.status_code == 200
    assert response.content == b"RIFFfake"
    assert client.get("/review/audio/review-999.wav").status_code == 404

    response = client.patch("/review/items/review-001.wav", json={"decision": "remove"})
    assert response.status_code == 200
    assert response.json()["decision"] == "remove"
    assert json.loads((directory / "manifest.json").read_text())[0]["decision"] == "remove"
    assert client.patch("/review/items/review-001.wav", json={"decision": "invalid"}).status_code == 422
    assert client.patch("/review/items/review-999.wav", json={"decision": "keep"}).status_code == 404


def test_review_unavailable_without_manifest(client):
    assert client.get("/review/items").status_code == 404
