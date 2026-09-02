# Marketplace Skill and Extension Install/Uninstall

## Goal

Make installed Skills and Extensions manageable from Marketplace. Skills keep
their existing search flow. Extensions get a dedicated manual npm install
flow because Extension package search is explicitly out of scope for this
iteration.

## User experience

Marketplace Skill and Extension cards use the same footer layout. The footer
keeps the card action area aligned even when descriptions have different
lengths. The destructive action is a small `trash-2` ghost button revealed on
card hover, with an accessible label and a confirmation modal before any
uninstall request is sent.

The Extension install dialog is separate from the Skill search dialog. It
explains that packages can be found at `https://pi.dev/packages`, accepts a
full command or package id, and previews the normalized command. These inputs
all resolve to the same install source:

```text
pi install npm:pi-mcp-adapter
pi install npm:pi-mcp-adapter
npm:pi-mcp-adapter
pi-mcp-adapter
```

The backend receives only the normalized package source. On success, the
dialog closes, the installed Extension list refreshes, and a success toast is
shown. On failure, the dialog stays open and an error toast explains the
failure.

Skill installation follows the same success/error interaction: disable the
active action while running, close the dialog and refresh on success, and keep
the dialog open with an error toast on failure.

## Backend design

Add explicit endpoints for:

```text
POST /api/market/extensions/install
POST /api/market/extensions/uninstall
POST /api/market/skills/uninstall
```

The Extension install handler validates a conservative npm package id (scoped
or unscoped, with an optional version/range supported by Pi) and rejects shell
metacharacters, arbitrary flags, git URLs, and extra command arguments. It
invokes Pi with an argument array, never a shell command string. A full
`pi install` prefix is accepted at the UI boundary for convenience and stripped
before validation. Uninstall uses the same source identity recorded by the
card and invokes Pi's package removal command.

After every successful mutation, the frontend re-fetches the resource catalog
so the installed Extension/Skill state is authoritative. Existing discovery
versus enablement semantics remain unchanged: installing a package does not
silently select it for every Agent.

## Frontend components

- Extend the existing Marketplace state with independent install mode and
  uninstall-confirm state.
- Keep Skill search results and install behavior in the existing flow.
- Render Extension install as a package-id form with inline command preview.
- Add shared toast messages for install/uninstall success and backend errors.
- Add shared card footer/action markup for Skills and Extensions.
- Keep all new controls keyboard accessible; hover-only visibility is paired
  with focus-visible visibility.

## Error handling and safety

Pi package installation runs arbitrary package code with the user's Pi
permissions. The Extension dialog includes the package-site link and the
exact normalized command so the user can review the source before installing.
The backend uses strict argument validation, subprocess timeouts, and clear
HTTP errors. No shell interpolation is used.

## Testing

- Unit-test package input normalization and rejection cases.
- Unit-test Skill/Extension install and uninstall subprocess argument lists and
  error mapping.
- Add API tests for successful and failed mutation responses.
- Run the existing full Python test suite and frontend desktop/mobile smoke
  checks. Verify footer alignment, confirmation behavior, loading state,
  success toast, and failure toast.

## Out of scope

- npm Registry or `pi.dev/packages` search.
- Automatic Extension enablement for existing Agents.
- Package README rendering or dependency auditing.
