# Chat, Market, and Lucide Fix Design

## Scope

This pass verifies and closes the remaining acceptance gaps from Issues #2, #7,
#8, and #11 without reverting later Market install/uninstall work. The existing
single-page Alpine.js frontend, FastAPI API, and Pi/TinyDB boundaries remain
unchanged.

## Design

- Market continues to consume `/api/resources` and keeps the existing skills.sh
  search/install flow. Uninstall is deliberately deferred. Its five tabs,
  catalog filtering, resource empty states, responsive cards, and navigation are
  validated together.
- Chat detail uses one viewport-fixed header whose left edge follows the desktop
  sidebar width and whose mobile position follows the mobile topbar. The
  conversation content reserves header space, while drawers remain above the
  header. The existing chat scroll and composer behavior remain intact.
- Title editing uses the existing `PATCH /api/chats/{id}` endpoint. The client
  keeps the full title in the draft, displays a truncated title, treats shared
  chats as read-only, and serializes save/cancel behavior so blur cannot issue a
  second request after Enter or Escape.
- Lucide remains the only UI icon source for controls and dynamic activity
  chips. The CDN script and one `renderIcons` helper stay in the no-bundler
  frontend. Static audits remove residual text glyphs, hand-authored icon SVGs,
  and obsolete mask selectors while preserving the brand logo.

## Validation

Run the repository's Python formatting, lint, type, and test commands plus
JavaScript syntax and diff checks. Start the local app and inspect the Market
tabs/catalog, Chat title/header at desktop and mobile widths, sidebar states,
dialogs, tables, drawers, and streaming/dynamic icon surfaces in a browser.
