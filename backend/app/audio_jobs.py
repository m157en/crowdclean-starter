"""Explicit, review-only processing for uploaded audio jobs."""

import tempfile
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AudioJob, AudioSegment


class JobProcessingError(ValueError):
    pass


def process_upload_job(db: Session, job: AudioJob) -> AudioJob:
    if job.source_type != "upload":
        raise JobProcessingError("Only uploaded audio is supported")
    if job.status != "queued":
        raise JobProcessingError("Only queued jobs can be processed")
    if not job.source_path:
        raise JobProcessingError("Upload path is missing")

    uploads = (settings.storage_dir / "uploads").resolve()
    source = Path(job.source_path).resolve()
    if not source.is_relative_to(uploads) or not source.is_file():
        raise JobProcessingError("Upload path is outside storage or missing")

    job.status = "processing"
    job.error_message = None
    db.commit()

    try:
        from app.audio_pipeline import analyze_wav
        from app.audio_preprocessing import prepare_audio

        with tempfile.TemporaryDirectory(prefix="crowdclean-job-") as tempdir:
            prepared = Path(tempdir) / "audio.wav"
            metadata = prepare_audio(source, prepared)
            result = analyze_wav(prepared)

        duration = float(metadata["duration_seconds"])
        segments = []
        for interval in result["speech_intervals"]:
            start = float(interval["start"])
            end = min(float(interval["end"]), duration)
            if not (0 <= start < end <= duration):
                raise ValueError("Invalid detected interval")
            segments.append(AudioSegment(
                job_id=job.id,
                start_seconds=start,
                end_seconds=end,
                label="possible_dj_shout",
                confidence=0.0,
                decision="pending",
            ))

        db.execute(delete(AudioSegment).where(AudioSegment.job_id == job.id))
        db.add_all(segments)
        job.duration_seconds = duration
        job.status = "completed"
        job.error_message = None
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:
        db.rollback()
        job.status = "failed"
        job.error_message = f"{type(exc).__name__}: {str(exc)[:400]}"
        db.commit()
        db.refresh(job)
        return job
