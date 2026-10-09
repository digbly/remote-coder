import logging
from datetime import date, timedelta
from types import SimpleNamespace

from app.core.logging import DailyFileHandler


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("app", logging.INFO, __file__, 1, message, (), None)


def _dated_file(directory, day: date):
    return directory / f"app-{day.isoformat()}.log"


def test_writes_to_file_named_with_today(tmp_path) -> None:
    handler = DailyFileHandler(str(tmp_path))
    handler.emit(_record("hello"))
    handler.close()

    assert "hello" in _dated_file(tmp_path, date.today()).read_text()


def test_rolls_over_to_new_file_when_day_changes(tmp_path, monkeypatch) -> None:
    today = date.today()
    tomorrow = today + timedelta(days=1)
    handler = DailyFileHandler(str(tmp_path))
    handler.emit(_record("day one"))

    monkeypatch.setattr("app.core.logging.date", SimpleNamespace(today=lambda: tomorrow))
    handler.emit(_record("day two"))
    handler.close()

    assert "day one" in _dated_file(tmp_path, today).read_text()
    assert "day two" in _dated_file(tmp_path, tomorrow).read_text()
