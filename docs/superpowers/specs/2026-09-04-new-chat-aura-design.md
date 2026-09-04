# New chat composer Aura design

## Scope

The empty-state new-chat composer will retain a three-row textarea and receive one
DaisyUI `aura aura-rainbow aura-lg` treatment around its complete card. Existing
conversation composers, send behavior, skill-command completion, and themes are
out of scope.

## Design

The Aura wrapper has the existing `.start-card` as its single direct child, as
required by DaisyUI. The card remains responsible for the textarea, agent picker,
and send control, so its layout and interaction behavior do not change.

The textarea and the mirrored skill-command highlight use a shared initial height
of 108px: three 25.5px text lines at the existing 15px/1.7 type setting, plus
28px of vertical padding. The existing input handler may still grow the textarea
to its 320px maximum when content requires it.

## Validation

Run formatter and backend/frontend checks, then inspect the new-chat empty state
at desktop and mobile viewport widths. Confirm the Aura surrounds the whole card,
the empty textarea starts at three lines, and sending or skill-command input still
works.
