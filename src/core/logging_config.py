"""Logging configuration with rotating file handler.

``LOG_DIR`` comes from ``.env`` (default under ``tmp/logs``); the directory is
created automatically. No ``print()`` anywhere in the codebase — use the ``apps``
logger inside apps and ``root`` outside.
"""

import os
from pathlib import Path

import environ

_env = environ.Env()
BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = Path(_env.str("LOG_DIR", default=str(BASE_DIR / "tmp" / "logs")))
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {module} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "presuplano_backend.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "apps": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
}
