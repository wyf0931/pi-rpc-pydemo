# `ops.sh` Port Argument Design

## Goal

Allow local Docker operations to choose the host port without editing `.env` or
the Compose file, while preserving the existing default behavior.

## Interface

`bin/ops.sh start [PORT]` and `bin/ops.sh restart [PORT]` accept an optional
numeric host port. If omitted, the script uses `OMA_PORT` and then `8000`. A
positional port overrides `OMA_PORT` for that invocation only. `status` also
accepts an optional port so an ephemeral start can be checked explicitly;
`stop` and `logs` keep their existing argument-free interface.

The container continues to listen on port `8000`; only the host-side Compose
mapping changes. The script validates the final port as an integer from 1
through 65535 and prints usage on invalid or extra arguments. Both `PORT` and
`-p PORT` forms are accepted.

## Validation

Validation covers shell syntax, default/env/explicit-port resolution, invalid
input, and the repository test suite. No Docker service topology or application
code changes are required.
