# User-owned data isolation

## Decision

The platform remains single-database and single-process, but every user-owned
domain record carries an explicit `user_id`. Normal users are scoped to their
own user id; admins can query all users. Marketplace Skills and Extensions are
global resources and remain admin-managed only.

## Ownership model

`agents`, `chats`, `autopilots`, `autopilot_runs`, and `shares` receive a
`user_id` field. Child records retain their existing parent references and must
also pass same-user validation when created or changed. Sessions remain
authentication records and are owned by `users`.

## Migration

Startup creates the built-in admin first, then runs an idempotent ownership
backfill. Existing Agents become admin-owned. Chats inherit from their Agent,
Autopilots inherit from their Agent, Runs inherit from Chat or Autopilot, and
Shares inherit from Chat; unresolved records fall back to admin. Pi session
ids, transcripts, message bodies, and files are not rewritten.

## Authorization

Route handlers use a shared user scope: admin queries are unfiltered, while
normal-user queries include `user_id == current_user.id`. Detail, mutation,
run, share, and file routes apply the same ownership check, not only list
routes. Marketplace install/uninstall routes require admin; resource discovery
remains global.

## Testing

Cover migration idempotence, legacy ownership, normal-user list/detail denial,
admin cross-user visibility, same-user parent validation, and admin-only
Marketplace mutations. Run the full Python validation suite and browser smoke
checks for admin and normal-user navigation.
