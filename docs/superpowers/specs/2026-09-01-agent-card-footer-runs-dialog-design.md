# Agent Card Footer and Runs Dialog Design

Agent cards will use one bottom footer row for chat count and the delete
control. The chat count stays left-aligned and the delete control moves into
the same flex row with automatic right alignment; protected agents simply omit
the control without changing the row layout.

The Autopilot run-history dialog will keep its title separator, add breathing
room before the action toolbar, and use the shorter `Run` label. Existing click
handlers and run behavior remain unchanged.
