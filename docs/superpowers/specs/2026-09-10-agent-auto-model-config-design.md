# Agent linked Auto model configuration design

## Goal

Let an Agent use the current platform defaults for Provider, model, and thinking level without persisting a brittle model ID. When an operator changes `PI_PROVIDER`, `PI_MODEL`, `PI_THINKING_LEVEL`, or the Pi `models.json` catalog, Auto Agents use the new defaults on their next short-lived Pi RPC process.

The new/edit Agent dialog exposes Auto as one linked choice. Auto never permits a mixed state such as an automatic Provider with a fixed model.

## Current behavior

Agent rows already allow nullable `provider`, `model`, and `thinking_level`. Pi command construction already resolves each falsey Agent value from the corresponding environment-backed setting:

```text
Agent provider/model/thinking_level
  -> null
  -> PI_PROVIDER / PI_MODEL / PI_THINKING_LEVEL
  -> Pi RPC command for the new session
```

The gap is the dialog: it always selects and persists concrete values. Existing rows that reference a removed model become hard to edit because the model is absent from the current catalog.

Production currently contains one affected Agent using `deepseek / deepseek-v4-pro / low`; the current catalog has renamed the usable model to `deepseek / deepseek-flash`.

## Design

### Persisted representation

`provider`, `model`, and `thinking_level` remain nullable; no schema migration is required.

| Mode | provider | model | thinking_level |
| --- | --- | --- | --- |
| Auto | `null` | `null` | `null` |
| Explicit | catalog provider ID | model ID from that provider | supported thinking level |

The backend rejects partial Auto payloads. The three values must be all null or all explicit and valid against the current resource catalog.

### API and runtime

Agent create/update validation gains a model-configuration validator:

- three null values are valid Auto;
- any partial null combination returns `422`;
- explicit values must use a discovered Provider, a model belonging to that Provider, and a supported thinking level;
- instruction generation follows the same validator and passes null values to the existing Pi fallback behavior when Auto is selected.

No persistent Pi process is introduced. Each Chat continues to start a short-lived RPC process, so Auto resolves the current defaults at session start.

### Dialog behavior

The Provider selector gets an `Auto (system default)` option. Selecting Auto clears and disables the model and thinking selectors, displays the current default triplet as helper text, and sends three null fields on save.

Selecting a concrete Provider enables model selection and sets a valid concrete model plus thinking level. An existing Agent whose explicit model no longer exists is shown as a stale configuration; the user can switch it to Auto or choose a valid explicit configuration before saving.

The same dialog remains the only edit/create surface. No new settings UI is introduced because the canonical defaults are the existing `PI_PROVIDER`, `PI_MODEL`, and `PI_THINKING_LEVEL` configuration.

### Production repair

After the code is merged and deployed, run a targeted, backed-up SQLite update for the one Agent referencing `deepseek-v4-pro`:

```text
provider       deepseek
model          deepseek-flash
thinking_level low
```

Only rows matching the removed model are changed. The operation verifies the post-update value and preserves a timestamped SQLite backup.

## Error handling

- An absent or invalid configured system default does not make Auto values valid in the edit API; the resource catalog must still expose the default Provider/model before an Auto Agent can be saved.
- When opening an existing stale explicit Agent, the dialog remains open and shows a clear stale-model state instead of silently changing the persisted configuration.
- Pi RPC errors remain mapped to existing `503` behavior; no credentials or prompts are logged.

## Tests

- API tests for Auto create/update, partial-Auto rejection, explicit validation, and stale explicit model handling.
- Pi command tests proving null Agent values inherit configured settings.
- Frontend static and browser tests for Auto selection, disabled dependent selectors, and explicit re-enablement.
- Store test proving nullable values preserve Auto across an Agent round-trip.
- Production maintenance command checks before/after row counts and backs up SQLite before update.

## Scope boundaries

- Does not add a database table for provider defaults.
- Does not change `models.json` or `auth.json` editing.
- Does not rewrite Agents with valid explicit configurations.
- Does not add partial Auto semantics.
