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
    assert client.get("/review/items").json() == []
    response = client.get("/review/audio/review-001.wav")
    assert response.status_code == 200
    assert response.content == b"RIFFfake"
    assert client.get("/review/audio/review-999.wav").status_code == 404

    response = client.patch("/review/items/review-001.wav", json={"decision": "remove"})
    assert response.status_code == 200
    assert response.json()["decision"] == "remove"
    assert client.get("/review/items").json()[0]["file"] == audio.name
    assert json.loads((directory / "manifest.json").read_text())[0]["decision"] == "remove"
    assert client.patch("/review/items/review-001.wav", json={"decision": "invalid"}).status_code == 422
    assert client.patch("/review/items/review-999.wav", json={"decision": "keep"}).status_code == 404


def test_review_unavailable_without_manifest(client):
    assert client.get("/review/items").status_code == 404


def test_precise_boundary_requires_remove_and_valid_range(client, tmp_path):
    directory = Path(tmp_path) / "analysis/review/threshold-03"
    directory.mkdir(parents=True)
    path = directory / "manifest.json"
    path.write_text(json.dumps([{"file": "review-001.wav", "start": 10.0,
        "end": 20.0, "detected_intervals": 1, "decision": "keep"}]))
    url = "/review/items/review-001.wav/boundary"
    assert client.put(url, json={"start": 12, "end": 13}).status_code == 409
    assert client.patch("/review/items/review-001.wav", json={"decision": "remove"}).status_code == 200
    assert client.put(url, json={"start": 9, "end": 13}).status_code == 422
    assert client.put(url, json={"start": 13, "end": 12}).status_code == 422
    assert client.put(url, json={"start": 12, "end": 13}).status_code == 200
    assert json.loads(path.read_text())[0]["precise_boundary"] == {"start": 12.0, "end": 13.0}
    assert client.patch("/review/items/review-001.wav", json={"decision": "keep"}).status_code == 200
    assert "precise_boundary" not in json.loads(path.read_text())[0]
