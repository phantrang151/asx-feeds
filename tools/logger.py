import logging
from contextvars import ContextVar
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"

# The current HTTP request's id, set by api/request_id.py's middleware for the duration of one
# request. A ContextVar (not a module global) so concurrent requests each see their own value -
# FastAPI copies it into the threadpool that runs sync endpoints. "-" outside any request
# (pipeline scripts, evals, startup).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_configured = False


class RequestIdFilter(logging.Filter):
    """Stamps every log record with the current request id, so LOG_FORMAT's %(request_id)s works
    for every module's logger without each call site passing it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """The one logging configuration for the app: file + console handlers on the root logger,
    each carrying RequestIdFilter. Every module logger (get_logger(__name__)) propagates to the
    root, so they all share it. Safe to call more than once - only the first call configures."""
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in (logging.FileHandler(LOG_DIR / "ticker_thesis.log"), logging.StreamHandler()):
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name - call as get_logger(__name__) so each log
    line shows which module wrote it. Also makes sure setup_logging() has run, so a module
    that logs is never left with Python's unconfigured default.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: Configured logger instance.
    """
    setup_logging()
    return logging.getLogger(name)
