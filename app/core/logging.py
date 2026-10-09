from logging.config import dictConfig

from app.core.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Uvicorn installs its own handlers and disables propagation; clear them so its
# records flow through the root handler and every log line shares one format.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


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
            },
            "loggers": {
                name: {"handlers": [], "propagate": True} for name in _UVICORN_LOGGERS
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console"],
            },
        }
    )
