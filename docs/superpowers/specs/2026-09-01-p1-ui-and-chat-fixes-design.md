# P1 UI and Chat Fixes Design

## Scope

This work covers the requested P1 issues in three bounded batches:

1. Page consistency and CSS: #14, #15, #19, #20, #21, #39, #40.
2. Chat loading, reasoning state/activity, and usage footer: #16, #17, #18, #37.
3. Standalone generated-file preview: #38.

The existing single-page Alpine frontend remains the only UI runtime. No API or
storage changes are planned unless inspection proves that Pi usage fields are
being dropped by the RPC bridge.

## Design

The first batch will consolidate only the selectors that are demonstrably shared
between the affected pages. Market cards will retain the existing DaisyUI card
markup and use a three-column desktop grid, inline identity row, scoped circular
avatar, and two-line description clamp. Library and Autopilot filters will share
the existing `filter-select` class and `--line` token. Their tables will share
the Autopilot visual reference without changing data or actions. The chat header
will keep its fixed positioning and mobile override while using compact desktop
padding. Dead CSS will be removed only when duplicate blocks are in the same
scope and the surviving declaration fully determines the result.

For Chat, message normalization will retain assistant usage and count only
`web_search`/`web_fetch` tool calls. Reasoning rendering will use stable keys
stored in Alpine state so poll refreshes do not reset the user's open/closed
choice. Web activity rows will expose parsed page links, with Lucide icons
rendered after Alpine HTML insertion through the existing icon observer.
Loading feedback will be an explicit centered DaisyUI indicator owned by the
message list state. The usage footer will be rendered only for the final
assistant answer and will stack above the existing actions on narrow screens.

The file preview will reuse the shared shell mode pattern, remove the chat UUID,
and add a viewport-edge back control using `history.back()` with a safe fallback
to the Library page. Its markdown rendering and existing sanitization pipeline
will remain unchanged.

## Validation

Each batch gets focused frontend inspection plus the repository test suite. The
final pass includes formatting, lint, type checking, tests, `git diff --check`,
and browser smoke checks at desktop/mobile widths in light/dark themes. The
untracked `issue19-desktop.png` is explicitly disposable and will be removed as
part of this work.
