# Chat viewport and composer design

## Goal

Make an existing conversation open at its newest message and make the detail
composer compact by default without losing room for multi-line prompts.

## Scope

- After the initial messages for an opened chat render, scroll the chat message
  viewport to its bottom.
- Keep that scroll limited to the initial view load. Later streaming and polling
  updates must not pull a user away from older history they are reading.
- Start the detail composer at one line. Resize it with its content through at
  most seven visible lines, then use textarea scrolling for the remaining text.
- Keep the send or abort button anchored to the composer’s lower-right edge on
  desktop and mobile.

## Design

`scrollMessagesToLatest` schedules its DOM read after Alpine has rendered the
loaded messages, then sets the message-list element’s `scrollTop` to its
`scrollHeight`. `openChat` invokes it only after applying the initial payload.

`resizeConversationInput` resets the textarea to its intrinsic height, measures
the line height, and clamps the resulting height to seven lines. It switches
overflow from hidden to automatic only at that limit. Sending, opening a chat,
and returning to an empty draft restore the one-line height.

The detail composer remains a positioned container; the existing absolute send
button remains bottom-aligned, while textarea padding reserves horizontal space
for it. CSS sets the one-line base height and derives the seven-line cap from
the same line-height on desktop and mobile.

## Validation

- Assert the static UI contract for one-line composer markup and the resize /
  initial-scroll helpers.
- Run formatting, linting, type checking, and the full test suite.
- Smoke check a loaded conversation and composer at desktop and mobile widths.
