# Pluggable Image Tools Design

## Goal

Expose stable `generate_image` and `edit_image` tools to OMA Agents while
keeping image generation separate from the Agent's chat Provider and Model.
The first automatic strategy is SenseNova U1.5 Lite; future providers implement
the same two operations behind the registry.

## Runtime

`PiRuntimeManager` loads `oma-image-tools.ts` only when an Agent selects an
image tool. The extension owns a small provider registry and resolves
`provider=auto` to SenseNova. It always requests Base64 from SenseNova, writes
the durable file to `PI_CWD/generated/<chat-id>/`, and returns the image plus a
structured output path. Chat Files and Library discover that path from the Pi
tool result.

The API key and SenseNova defaults are process configuration. They are copied
into Pi's child-process environment, never returned by APIs, persisted to
SQLite, or logged.

## Authorization

`edit_image` may send only an image the user uploaded to the current Chat or an
image previously created by the image tools in that same Chat. Pi session IDs
are deliberately equal to OMA chat IDs, so the extension verifies the upload
prefix and generated-file provenance against the session transcript before
reading input bytes.

## Vision input

OMA encodes authorized image uploads and attached Chat artifacts into Pi RPC's
native `prompt.images` field. The chat model can therefore describe an image
directly when its selected model supports vision; no separate `describe_image`
tool is introduced.

## Known limit

Pi persists image blocks as Base64 in session history. The first release returns
an inline preview to satisfy Chat rendering. Issue #131 tracks a bounded,
non-destructive image-context policy before high-volume image workflows.
