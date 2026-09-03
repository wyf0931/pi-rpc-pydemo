# Agent Marketplace publish and install

## Decision

An Agent in `agents` is always a user-owned working copy. Marketplace entries
are immutable publication snapshots. Publishing never exposes the live Agent
record, and installing always creates a new Agent record owned by the current
user.

There is no system-default Agent. A user may create an Agent or install one
from the Marketplace when starting a Chat or Autopilot.

## Data model

`agent_publications` stores the listing identity, author, latest version, and
install count. `agent_publication_versions` stores a canonical JSON snapshot
of the Agent behavior and its SHA-256 hash. A publication version is immutable.

An installed Agent records `source_publication_id`, `source_version`, and
`source_hash`; its own `content_hash` is recalculated when publishing or
updating. Publication visibility is organization-wide, while editing and
publishing remain restricted to the Agent owner.

## API

- `GET /api/market/agents` lists organization publications and latest versions.
- `POST /api/agents/{id}/publish` creates a publication or a new version after
  verifying ownership and accepting a SemVer version.
- `POST /api/market/agents/{publication_id}/install` copies the latest or
  requested version into the current user's Agents and increments installs.

The install endpoint returns the new private Agent. Duplicate installation is
allowed because each install is an intentional independent copy.

## UI

Owned Agent cards show an RSS publish action beside the existing delete action.
The publish dialog requires a version and explains organization visibility.
Marketplace Agents use the existing Agent card visual language, with a User
author label, an install count, and a right-side ghost plus action. Both
publish and install require confirmation and show success/error toast feedback.

## Safety and compatibility

Only behavior configuration is snapshotted; ids, ownership, timestamps, chat
counts, and protected flags are excluded from the content hash. Existing Agents
remain private and are not implicitly published. The old placeholder tab is
replaced with an empty state when no publication exists.
