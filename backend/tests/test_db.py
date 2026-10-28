from unittest.mock import Mock

import pytest

from app import db


def test_get_db_closes_session_after_normal_use(monkeypatch):
    session = Mock()
    monkeypatch.setattr(db, "SessionLocal", lambda: session)

    generator = db.get_db()

    assert next(generator) is session

    with pytest.raises(StopIteration):
        next(generator)

    session.close.assert_called_once_with()


def test_get_db_closes_session_after_exception(monkeypatch):
    session = Mock()
    monkeypatch.setattr(db, "SessionLocal", lambda: session)

    generator = db.get_db()

    assert next(generator) is session

    with pytest.raises(RuntimeError, match="simulated error"):
        generator.throw(RuntimeError("simulated error"))

    session.close.assert_called_once_with()
