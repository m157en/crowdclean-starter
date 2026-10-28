import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.audio_storage import InvalidAudioFile, persist_upload
from app.config import settings


def test_persist_upload_saves_file_and_sanitizes_filename(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)

    content = b"fake-audio-content"
    upload = UploadFile(
        filename="../Festival.MP3",
        file=BytesIO(content),
    )

    stored_path, original_name, size = asyncio.run(
        persist_upload(upload)
    )

    assert original_name == "Festival.MP3"
    assert size == len(content)
    assert Path(stored_path).read_bytes() == content
    assert upload.file.closed


def test_oversized_upload_is_rejected_and_removed(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "max_upload_bytes", 5)

    upload = UploadFile(
        filename="set.mp3",
        file=BytesIO(b"123456"),
    )

    with pytest.raises(InvalidAudioFile, match="upload limit"):
        asyncio.run(persist_upload(upload))

    assert list((tmp_path / "uploads").iterdir()) == []
    assert upload.file.closed


def test_empty_upload_is_rejected_and_removed(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)

    upload = UploadFile(
        filename="empty.mp3",
        file=BytesIO(b""),
    )

    with pytest.raises(InvalidAudioFile, match="empty"):
        asyncio.run(persist_upload(upload))

    assert list((tmp_path / "uploads").iterdir()) == []
    assert upload.file.closed
