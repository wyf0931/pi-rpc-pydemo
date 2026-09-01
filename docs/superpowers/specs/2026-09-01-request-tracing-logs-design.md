# Request Tracing and Persistent Logs Design

## Goal

Make production failures retrospectively searchable with one request ID, while
keeping the local-first MVP lightweight and avoiding a tracing backend.

## Design

- Configure Python's standard `logging` once at application startup/import with
  a JSON-lines formatter. Emit to stdout for `docker compose logs` and to a
  rotating file under the configured log directory for post-crash inspection.
- Add an ASGI middleware that accepts a valid incoming `X-Request-ID` or
  generates a UUID4, binds it to a context variable, logs request completion
  (`method`, `path`, `status_code`, `duration_ms`, `request_id`), and returns the
  ID in the response header. Exception paths log the exception and still
  preserve the request ID.
- Add structured business events around Market search/install and Pi RPC
  process/operation failures. Never log prompt bodies, model output, provider
  credentials, or authorization material. Use `trace_id` as a future-compatible
  alias for the request ID and reserve `span_id` for later instrumentation.
- Make the frontend request helper generate an ID per HTTP request, send it as
  `X-Request-ID`, read the response ID, and handle non-JSON responses without
  leaking a browser `Unexpected token '<'` parser error. User-facing errors
  include the request ID when available.
- Add a host-configurable Compose bind mount `${PI_LOG_DIR:-./logs}:/app/logs`.
  The application receives `PI_LOG_DIR=/app/logs`; rotation limits local disk
  growth while keeping logs outside the container writable layer.

## Validation

Test request ID generation/propagation, JSONL fields, exception logging,
non-JSON API responses, and log directory configuration. Run the full Python
quality gate and browser smoke the Market install error path. Validate the
Compose configuration and document the new `PI_LOG_DIR` setting.
