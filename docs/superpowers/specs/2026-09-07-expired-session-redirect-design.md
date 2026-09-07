# Expired-session redirect design

## Goal

Return users to sign-in cleanly when an authenticated browser session expires
while the application remains open.

## Scope

- Centralize HTTP 401 handling in the existing front-end `api()` wrapper.
- Clear the local user and active workspace view state.
- Show one warning that the login session has expired, then render the existing
  login screen.
- Preserve HTTP 403 responses as ordinary authorization errors.

## Design

The API wrapper recognizes a non-login 401 before constructing the generic
request error. It calls one idempotent session-expiry handler that stops active
chat observers, clears local authenticated state, returns the client route to
the chat landing page, and sets a user-facing warning. The handler does not
call the logout endpoint because the server has already rejected the cookie;
the next login overwrites it.

The initial `/api/auth/session` probe remains a passive check: it must not show
the expiry warning when a user first opens the site without a session. Calls to
the login endpoint also keep their existing invalid-credentials behavior.

## Validation

- Static UI regression test asserts central 401 handling and 403 preservation.
- Run formatting, linting, type checks, and the full test suite.
