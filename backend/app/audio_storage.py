from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings


class InvalidAudioFile(ValueError):
    pass


async def persist_upload(upload: UploadFile) -> tuple[str, str, int]:
    """Persist an upload in bounded chunks; return path, safe filename, and bytes written."""
    original_name = Path(upload.filename or "audio").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in settings.allowed_audio_extensions:
        raise InvalidAudioFile(
            f"Unsupported audio extension '{suffix or '[none]'}'. Supported: {', '.join(settings.allowed_audio_extensions)}"
        )

    upload_dir = settings.storage_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid4().hex}{suffix}"
    bytes_written = 0
    try:
        with stored_path.open("wb") as destination:
            while chunk := await upload.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_bytes:
                    raise InvalidAudioFile(f"File exceeds the {settings.max_upload_bytes}-byte upload limit")
                destination.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if bytes_written == 0:
        stored_path.unlink(missing_ok=True)
        raise InvalidAudioFile("The uploaded file is empty")

    return str(stored_path), original_name, bytes_written
