import json
import logging
import logging.handlers
import re
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_request_id: ContextVar[str] = ContextVar("oma_request_id", default="-")
_logging_configured = False


def current_request_id() -> str:
    return _request_id.get()


def _request_id_from(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else str(uuid4())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", current_request_id()),
        }
        payload["trace_id"] = payload["request_id"]
        for name in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "operation",
            "pi_stderr",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path) -> None:
    global _logging_configured
    if _logging_configured:
        return
    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = None
    file_error: OSError | None = None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "oma-studio.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
    except OSError as exc:
        file_error = exc
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(stream_handler)
    if file_handler:
        root.addHandler(file_handler)
    _logging_configured = True
    if file_error:
        root.error(
            "persistent log file unavailable",
            extra={
                "event": "logging.file.unavailable",
                "operation": "configure",
                "pi_stderr": str(file_error),
            },
        )


async def trace_request(request: Request, call_next) -> Response:
    request_id = _request_id_from(request)
    token = _request_id.set(request_id)
    started = time.perf_counter()
    logger = logging.getLogger("oma.http")
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed",
            extra={
                "event": "http.request.failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": request_id},
            status_code=500,
        )
    finally:
        _request_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    log_method = logger.warning if response.status_code >= 400 else logger.info
    log_method(
        "request completed",
        extra={
            "event": (
                "http.request.error"
                if response.status_code >= 400
                else "http.request.completed"
            ),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "request_id": request_id,
        },
    )
    return response
