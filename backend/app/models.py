from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AudioJob(Base):
    __tablename__ = "audio_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # url | upload
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    segments: Mapped[list["AudioSegment"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="AudioSegment.start_seconds"
    )


class AudioSegment(Base):
    __tablename__ = "audio_segments"
    __table_args__ = (
        CheckConstraint("start_seconds >= 0", name="ck_audio_segments_start_nonnegative"),
        CheckConstraint("end_seconds > start_seconds", name="ck_audio_segments_end_after_start"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_audio_segments_confidence_range"),
        CheckConstraint("decision IN ('pending', 'keep', 'remove')", name="ck_audio_segments_decision_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("audio_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False, default="possible_dj_shout")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | keep | remove

    job: Mapped[AudioJob] = relationship(back_populates="segments")
