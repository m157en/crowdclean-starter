from datetime import datetime
from typing import Optional

import strawberry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioJob, AudioSegment


@strawberry.type
class AudioJobType:
    id: str
    source_type: str
    source_url: Optional[str]
    original_filename: Optional[str]
    status: str
    duration_seconds: Optional[float]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, job: AudioJob) -> "AudioJobType":
        return cls(
            id=job.id,
            source_type=job.source_type,
            source_url=job.source_url,
            original_filename=job.original_filename,
            status=job.status,
            duration_seconds=job.duration_seconds,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


@strawberry.type
class AudioSegmentType:
    id: int
    job_id: str
    start_seconds: float
    end_seconds: float
    label: str
    confidence: float
    decision: str

    @classmethod
    def from_model(cls, segment: AudioSegment) -> "AudioSegmentType":
        return cls(
            id=segment.id,
            job_id=segment.job_id,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            label=segment.label,
            confidence=segment.confidence,
            decision=segment.decision,
        )


@strawberry.type
class Query:
    @strawberry.field
    def service_status(self) -> str:
        return "ok"

    @strawberry.field
    def jobs(self, info: strawberry.Info) -> list[AudioJobType]:
        db: Session = info.context["db"]
        jobs = db.scalars(select(AudioJob).order_by(AudioJob.created_at.desc(), AudioJob.id)).all()
        return [AudioJobType.from_model(job) for job in jobs]

    @strawberry.field
    def job(self, info: strawberry.Info, id: str) -> Optional[AudioJobType]:
        db: Session = info.context["db"]
        job = db.get(AudioJob, id)
        return AudioJobType.from_model(job) if job else None

    @strawberry.field
    def segments(self, info: strawberry.Info, job_id: str) -> list[AudioSegmentType]:
        db: Session = info.context["db"]
        segments = db.scalars(
            select(AudioSegment).where(AudioSegment.job_id == job_id).order_by(AudioSegment.start_seconds)
        ).all()
        return [AudioSegmentType.from_model(segment) for segment in segments]


@strawberry.type
class Mutation:
    @strawberry.mutation
    def update_segment_decision(self, info: strawberry.Info, segment_id: int, decision: str) -> Optional[AudioSegmentType]:
        if decision not in {"pending", "keep", "remove"}:
            raise ValueError("decision must be one of: pending, keep, remove")
        db: Session = info.context["db"]
        segment = db.get(AudioSegment, segment_id)
        if segment is None:
            return None
        segment.decision = decision
        db.commit()
        db.refresh(segment)
        return AudioSegmentType.from_model(segment)


schema = strawberry.Schema(query=Query, mutation=Mutation)
