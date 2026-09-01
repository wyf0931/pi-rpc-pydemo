# Issue #27 Agent Card Identity Design

The Agent card identity row will explicitly override the generic `.card-top`
space-between layout with left alignment and the same 12px gap used by Market
cards. The name will flex into the remaining row width and keep the existing
ellipsis behavior. This is a CSS-only change; card actions, data, and responsive
grid behavior remain unchanged.

Validation will use Chrome DevTools on `/agents` at desktop and narrow widths,
checking that the avatar and name are adjacent, then run the repository test and
diff checks.
