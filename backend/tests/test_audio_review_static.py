import json
from pathlib import Path

import pytest

from app.audio_review_static import export_review


def make_report(folder: Path, unsafe=False):
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("review-006-original.wav", "review-006-selective.wav",
                 "review-006-partial.wav", "review-006-spectral.wav"):
        (folder / name).write_bytes(b"placeholder wav")
    files = ["review-006-selective.wav", "review-006-partial.wav",
             "../traversal.wav" if unsafe else "review-006-spectral.wav"]
    (folder / "report.json").write_text(json.dumps({"items": [
        {"source_episode": "review-006", "episode": "review-006-" + name.split("-")[-1],
         "method": method, "original": "review-006-original.wav", "preview": name}
        for name, method in zip(files, ("selective", "partial", "spectral"))
    ]}), encoding="utf-8")


def test_static_review_export_without_server(tmp_path):
    make_report(tmp_path)
    page = export_review(tmp_path)
    content = page.read_text(encoding="utf-8")
    assert content.count("<audio controls") == 4
    assert 'review-006-selective.wav' in content
    assert 'review-006-spectral.wav' in content
    with pytest.raises(FileExistsError):
        export_review(tmp_path)


def test_static_review_blocks_path_traversal(tmp_path):
    make_report(tmp_path, unsafe=True)
    with pytest.raises(ValueError, match="Unsafe audio path"):
        export_review(tmp_path)
    assert not (tmp_path / "listen-v3.html").exists()
