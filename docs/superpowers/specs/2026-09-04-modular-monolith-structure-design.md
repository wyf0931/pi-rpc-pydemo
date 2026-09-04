# Modular monolith structure

## Decision

OMA Studio will remain a single FastAPI process and a single Docker Compose
service. The change introduces explicit package boundaries for HTTP delivery,
business domains, platform infrastructure, and application composition. It
does not change API paths, response payloads, TinyDB data, Pi session ids, Pi
transcripts, authorization rules, or Docker's one-process runtime model.

TinyDB remains the only persistence implementation. This refactor may place
TinyDB code behind domain-oriented modules, but it must not introduce a
database-neutral repository framework, SQLite code, migrations, or speculative
interfaces for a future replacement.

## Target ownership

The application will move incrementally toward this layout:

```text
src/oma_studio/
  api/
    app.py                  # application factory and route registration
    dependencies.py         # request-scoped FastAPI dependencies
    middleware.py           # authentication and request middleware
    routers/                # HTTP handlers and Pydantic transport models
  domains/
    identity/
    agents/
    chats/
    artifacts/
    marketplace/
    autopilots/
    shares/
  infrastructure/
    persistence/            # TinyDB implementation, grouped by domain
    pi/                     # Pi RPC process runtime
    resource_catalog/       # discovery of Pi-managed capabilities
  core/
    config.py
    lifecycle.py
    logging.py
    errors.py
  web/                      # static browser application assets
```

Package names describe product concepts. In particular, `files` becomes
`artifacts`, `resources` becomes `resource_catalog`, and `market` becomes
`marketplace`. `app` is a transitional import package and will eventually
become `oma_studio` under `src/`.

## Composition and lifecycle

`create_app()` becomes the only composition root. It obtains settings, creates
the TinyDB store and Pi runtime, configures logging and middleware, and
registers routers and static assets. Application resources are held in typed
application state or explicit dependencies rather than module globals.

FastAPI lifespan owns startup and shutdown. The scheduler starts before the
application receives requests; scheduler and Pi runtime cleanup happens after
request handling stops. Existing single-worker deployment remains required
because active Pi processes and per-chat locks are process-local.

## Dependency direction

HTTP routers may call domain services and FastAPI dependencies. Domains may
use the concrete TinyDB and Pi capabilities required today. Infrastructure
must not import HTTP routers or request objects. Core modules must not import
domains or infrastructure.

There is no mandatory service class per entity. A domain gets a service module
only where it has orchestration beyond a route handler or persistence method.
Likewise, TinyDB modules are split only by existing aggregate ownership rather
than by a generic repository hierarchy.

## Migration sequence

1. Add an application factory and lifespan while retaining `app.main:app` as a
   compatible ASGI target.
2. Extract shared HTTP dependencies and middleware without changing route
   behavior.
3. Move routes and their Pydantic request models by product area. Preserve all
   existing URLs and public response formats.
4. Relocate existing modules into their target packages using compatibility
   imports only for in-repository callers during the migration.
5. Split TinyDB persistence by existing aggregate ownership. Do not alter the
   JSON document schema or add a persistence abstraction.
6. Migrate to `src/oma_studio`, update packaging, Docker and commands, then
   remove compatibility modules in a separate release.
7. Reorganize tests into unit, integration, and contract scopes after the
   application factory gives each test an isolated composition point.

Each step is independently reviewable and must leave `uv run pytest -q`, Ruff,
Pyright, Docker Compose startup, and the existing browser smoke flow green.

## Delivery configuration

The root Compose file continues to provide the fast local path. A production
overlay and a production environment example will make deployment-specific
ports, image tags, mounted state, and logging explicit. Private deployments
continue to use host-mounted Pi state and workspace directories. This change
does not claim that `PI_CWD` is a sandbox.

## Out of scope

- SQLite, database migrations, ORM adoption, or a database-agnostic layer
- microservices, queues, worker processes, or horizontal replication
- frontend framework replacement or a JavaScript bundler
- public API version-path changes
- changes to Pi message ownership or chat-id/session-id identity
