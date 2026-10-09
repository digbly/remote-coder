from datetime import date
from logging import FileHandler, LogRecord
from logging.config import dictConfig
from pathlib import Path

from app.core.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Uvicorn installs its own handlers and disables propagation; clear them so its
# records flow through the root handler and every log line shares one format.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class DailyFileHandler(FileHandler):
    """File handler writing to ``<directory>/<prefix>-YYYY-MM-DD<suffix>``.

    The target file is derived from the current date on each record, so the
    handler rolls over to a new dated file at midnight without a restart.
    """

    def __init__(
        self,
        directory: str,
        prefix: str = "app",
        suffix: str = ".log",
        encoding: str = "utf-8",
    ) -> None:
        self._directory = Path(directory)
        self._prefix = prefix
        self._suffix = suffix
        self._current_day = date.today()
        super().__init__(self._path_for(self._current_day), encoding=encoding, delay=True)

    def _path_for(self, day: date) -> str:
        return str((self._directory / f"{self._prefix}-{day.isoformat()}{self._suffix}").resolve())

    def _roll_to(self, day: date) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        self._directory.mkdir(parents=True, exist_ok=True)
        self.baseFilename = self._path_for(day)
        self.stream = self._open()

    def emit(self, record: LogRecord) -> None:
        today = date.today()
        if today != self._current_day or self.stream is None:
            self._current_day = today
            self._roll_to(today)
        super().emit(record)


def configure_logging(settings: Settings) -> None:
    """Configure application-wide logging from the active settings."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": LOG_FORMAT,
                    "datefmt": DATE_FORMAT,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                },
                "file": {
                    "()": "app.core.logging.DailyFileHandler",
                    "formatter": "default",
                    "directory": settings.log_dir,
                },
            },
            "loggers": {
                name: {"handlers": [], "propagate": True} for name in _UVICORN_LOGGERS
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console", "file"],
            },
        }
    )
