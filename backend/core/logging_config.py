"""
JUALIN.AI — Structured Logging Configuration
JSON-formatted logs with request ID tracking, colored console output,
and production-ready file rotation.

Usage:
    from core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("User registered", extra={"user_id": 1, "email": "a@b.com"})
"""
import logging
import json
import sys
import os
from datetime import datetime, timezone
from contextvars import ContextVar

# ── Context Variables (thread-safe request tracking) ──
# These are set per-request by the RequestIDMiddleware
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
request_path_var: ContextVar[str] = ContextVar("request_path", default="-")


# ══════════════════════════════════════════════════
# JSON Formatter — Production logs (file / aggregation)
# ══════════════════════════════════════════════════

class JSONFormatter(logging.Formatter):
    """
    Outputs each log record as a single-line JSON object.
    This format is ideal for log aggregation tools (ELK, Loki, etc.)
    and structured log analysis.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": request_id_var.get("-"),
            "path": request_path_var.get("-"),
        }

        # Merge any extra fields passed via logger.info(..., extra={...})
        # Exclude standard LogRecord attributes to avoid duplication
        _STANDARD_ATTRS = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "thread", "threadName", "process",
            "processName", "levelname", "levelno", "message", "msecs",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                log_entry[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ══════════════════════════════════════════════════
# Console Formatter — Development logs (colored, readable)
# ══════════════════════════════════════════════════

class ColoredConsoleFormatter(logging.Formatter):
    """
    Human-readable colored output for development.
    Format: [TIME] LEVEL  module | message {extras}
    """

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        req_id = request_id_var.get("-")
        req_id_short = req_id[:8] if req_id != "-" else "-"

        time_str = datetime.now().strftime("%H:%M:%S")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        module = f"{self.DIM}{record.module}{self.RESET}"
        message = record.getMessage()

        # Build extra fields string (if any meaningful extras)
        _STANDARD_ATTRS = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "thread", "threadName", "process",
            "processName", "levelname", "levelno", "message", "msecs",
            "taskName",
        }
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and not k.startswith("_")
        }
        extra_str = f" {self.DIM}{extras}{self.RESET}" if extras else ""

        line = f"{self.DIM}[{time_str}]{self.RESET} {level} {module} | {message}{extra_str}"

        if req_id_short != "-":
            line = f"{self.DIM}[{time_str}]{self.RESET} {level} {self.DIM}[{req_id_short}]{self.RESET} {module} | {message}{extra_str}"

        # Append traceback if present
        if record.exc_info and record.exc_info[1]:
            line += f"\n{self.formatException(record.exc_info)}"

        return line


# ══════════════════════════════════════════════════
# Logger Factory
# ══════════════════════════════════════════════════

_configured = False


def setup_logging(log_level: str = "INFO", log_to_file: bool = False, log_dir: str = "logs"):
    """
    Configure the root logger ONCE for the entire application.
    Call this during app startup (lifespan).

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to also write JSON logs to a file
        log_dir: Directory for log files (relative to backend/)
    """
    global _configured
    if _configured:
        return
    _configured = True

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove any existing handlers (prevent duplicates on reload)
    root_logger.handlers.clear()

    # 1. Console handler (always enabled, colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredConsoleFormatter())
    console_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)

    # 2. File handler (optional, JSON format for production)
    if log_to_file:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "jualin.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        file_handler.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


# Need this import here (after class definitions) for RotatingFileHandler
import logging.handlers


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("Something happened")
        logger.error("Failed to process", exc_info=True)
        logger.info("Order created", extra={"order_id": 42, "total": 89000})
    """
    return logging.getLogger(name)
