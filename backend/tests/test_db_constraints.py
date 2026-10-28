import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AudioJob, AudioSegment


def test_segment_constraints_reject_negative_start(db_session):
    job = AudioJob(source_type="url", source_url="https://example.com/set.mp3")
    db_session.add(job)
    db_session.flush()
    db_session.add(AudioSegment(job_id=job.id, start_seconds=-1.0, end_seconds=2.0, confidence=0.5))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_segment_constraints_reject_end_before_start(db_session):
    job = AudioJob(source_type="url", source_url="https://example.com/set.mp3")
    db_session.add(job)
    db_session.flush()
    db_session.add(AudioSegment(job_id=job.id, start_seconds=5.0, end_seconds=4.0, confidence=0.5))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_segment_constraints_reject_confidence_above_one(db_session):
    job = AudioJob(source_type="url", source_url="https://example.com/set.mp3")
    db_session.add(job)
    db_session.flush()
    db_session.add(AudioSegment(job_id=job.id, start_seconds=2.0, end_seconds=4.0, confidence=1.5))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
