# Settings theme preference design

## Scope

Settings → General is the sole theme control. A new visitor defaults to the
`system` preference, which is persisted in browser local storage. The sidebar
light/dark toggle is removed.

## State and behavior

`oma-theme-preference` is the only persisted theme preference and accepts
`system`, `light`, or `dark`. On initialization, a missing or invalid value is
normalized to `system` and saved. The application derives its active DaisyUI
`data-theme` from that preference.

When the preference is `system`, a `prefers-color-scheme` media-query listener
updates the active theme as the operating-system appearance changes. Explicit
Light and Dark preferences ignore system changes. The existing Settings General
controls continue to set the preference and apply it immediately.

## Migration

The legacy `pi-theme` key is no longer written or read. Existing users with no
valid `oma-theme-preference` receive the new `system` default on their next
visit.

## Validation

Add static integration coverage for default persistence, System/Light/Dark
preference handling, the system-theme listener, and removal of the sidebar
toggle. Run formatters, type checks, and the full test suite; perform a local
desktop and mobile smoke check when browser automation is available.
