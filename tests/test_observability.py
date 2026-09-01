import json
import logging

from app.observability import JsonFormatter, current_request_id


def test_json_formatter_includes_request_and_trace_ids():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.event = "http.request.completed"
    record.request_id = "req-123"
    record.status_code = 200

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "http.request.completed"
    assert payload["request_id"] == "req-123"
    assert payload["trace_id"] == "req-123"
    assert payload["status_code"] == 200


def test_request_context_defaults_to_empty_marker():
    assert current_request_id() == "-"
