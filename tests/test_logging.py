import logging
from datetime import date, timedelta
from types import SimpleNamespace

from app.core.config import Settings
from app.core.logging import DailyFileHandler, configure_logging


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("app", logging.INFO, __file__, 1, message, (), None)


def _dated_file(directory, day: date):
    return directory / f"app-{day.isoformat()}.log"


def _capture_config(monkeypatch, settings: Settings) -> dict:
    captured: dict = {}
    monkeypatch.setattr("app.core.logging.dictConfig", captured.update)
    configure_logging(settings)
    return captured


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


def test_access_logs_are_routed_to_access_file(tmp_path, monkeypatch) -> None:
    config = _capture_config(
        monkeypatch, Settings(log_dir=str(tmp_path), log_level="INFO")
    )

    assert config["loggers"]["uvicorn.access"]["handlers"] == ["access"]
    assert config["handlers"]["access"]["prefix"] == "access"
    assert config["handlers"]["access"]["level"] == "INFO"


def test_warnings_and_above_are_routed_to_error_file(tmp_path, monkeypatch) -> None:
    config = _capture_config(
        monkeypatch, Settings(log_dir=str(tmp_path), log_level="INFO")
    )

    assert config["handlers"]["error"]["prefix"] == "error"
    assert config["handlers"]["error"]["level"] == "WARNING"
    assert config["root"]["handlers"] == ["console", "error"]


def test_root_stays_verbose_for_error_threshold(tmp_path, monkeypatch) -> None:
    config = _capture_config(
        monkeypatch, Settings(log_dir=str(tmp_path), log_level="ERROR")
    )

    assert config["root"]["level"] == "WARNING"

