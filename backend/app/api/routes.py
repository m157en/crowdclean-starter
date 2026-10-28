from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audio_storage import InvalidAudioFile, persist_upload
from app.db import get_db
from app.models import AudioJob, AudioSegment
from app.schemas import (
    AudioJobRead,
    AudioSegmentRead,
    CreateUrlJob,
    JobListRead,
    SegmentDecisionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["audio jobs"])


@router.post("/jobs/url", response_model=AudioJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_url_job(payload: CreateUrlJob, db: Session = Depends(get_db)) -> AudioJob:
    job = AudioJob(source_type="url", source_url=str(payload.source_url), status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/upload", response_model=AudioJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_upload_job(file: UploadFile = File(...), db: Session = Depends(get_db)) -> AudioJob:
    try:
        stored_path, original_filename, _bytes_written = await persist_upload(file)
    except InvalidAudioFile as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    job = AudioJob(
        source_type="upload",
        original_filename=original_filename,
        source_path=stored_path,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=JobListRead)
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobListRead:
    total = db.scalar(select(func.count()).select_from(AudioJob)) or 0
    items = db.scalars(
        select(AudioJob).order_by(AudioJob.created_at.desc(), AudioJob.id).limit(limit).offset(offset)
    ).all()
    return JobListRead(items=items, limit=limit, offset=offset, total=total)


@router.get("/jobs/{job_id}", response_model=AudioJobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> AudioJob:
    job = db.get(AudioJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")
    return job


@router.get("/jobs/{job_id}/segments", response_model=list[AudioSegmentRead])
def list_segments(job_id: str, db: Session = Depends(get_db)) -> list[AudioSegment]:
    if db.get(AudioJob, job_id) is None:
        raise HTTPException(status_code=404, detail="Audio job not found")
    return list(db.scalars(select(AudioSegment).where(AudioSegment.job_id == job_id).order_by(AudioSegment.start_seconds)).all())


@router.patch("/segments/{segment_id}", response_model=AudioSegmentRead)
def update_segment_decision(
    segment_id: int,
    payload: SegmentDecisionUpdate,
    db: Session = Depends(get_db),
) -> AudioSegment:
    segment = db.get(AudioSegment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Audio segment not found")
    segment.decision = payload.decision
    db.commit()
    db.refresh(segment)
    return segment
