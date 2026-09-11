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
the durable file to `PI_CWD/generated/<chat-id>/`, and returns a structured
output path. Chat Files and Library discover that path from the Pi tool result;
the browser-native file endpoint opens images instead of embedding previews in
the transcript.

## Chat presentation and refresh

The production chat view accumulates successful image-tool outputs while the
turn is reasoning, then renders them after the complete reasoning/tool phase
and before the final answer. It uses the authorized browser file URL, shows no
tool metadata, and opens the original in a new tab on click. The image keeps its
aspect ratio and is bounded by the message width and viewport height on desktop,
tablet, and mobile layouts.

The Files drawer refreshes whenever it is opened and after a completed turn if
it is already open. This is intentionally independent of tool names, so normal
write/edit/publish artifacts and image outputs stay in sync through the same
path.

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

Pi persists user-image blocks as Base64 in session history. Generated-image tool
results intentionally return a file reference rather than Base64. Issue #131
tracks a bounded, non-destructive image-context policy before high-volume image
workflows.
