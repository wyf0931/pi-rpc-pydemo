# Settings Users tab

## Decision

User administration moves from its standalone sidebar-triggered dialog into a
Users tab in the existing Settings dialog. Settings becomes the single entry
point for user management. The existing API, administrator authorization
checks, user list, creation, enable/disable, and deletion behavior do not
change.

## Navigation and visibility

- Remove the sidebar Users icon and its standalone Users dialog.
- Keep Settings opening on the General tab.
- Add a Users item to the Settings navigation only when the signed-in user has
  the admin role.
- Render the Users content only for an admin. A normal user must neither see
  the tab nor receive an alternative client-side entry point.

## Users content

The Users tab uses the Settings dialog's header, content-column, section, and
responsive layout conventions. Its content preserves the existing users table
and its actions: user count, Add user action, account status toggle, and delete
action. The existing Add user and deletion-confirmation dialogs remain as
focused child dialogs.

Opening the Users tab loads the current user list. Creating, toggling, or
deleting a user refreshes that list exactly as it does today.

## Scope

This is a frontend interaction and layout consolidation only. It does not add
roles, pagination, search, API endpoints, user fields, or new authorization
rules. It does not change the administrator-only server-side checks.

## Verification

Cover the removed sidebar entry and the new Settings tab in static markup
checks. Run the full existing Python and frontend formatting gates. Perform a
desktop and mobile browser smoke check as required for UI changes, confirming
that the General tab still opens normally, admin Users management works, and a
normal user cannot see the Users tab.
