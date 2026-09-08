"""Backfill ownership after the TinyDB-to-SQLite migration."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Platform data directory")
    parser.add_argument("--apply", action="store_true", help="Write ownership changes")
    args = parser.parse_args()
    data_dir = (args.data or get_settings().data_dir).expanduser()
    store = Store(data_dir / "platform.json")
    admin = store.get_user_by_username("admin")
    if not admin:
        raise SystemExit("admin user not found; start the app once before backfilling")
    admin_id = admin["id"]
    changes = 0

    def update(table: str, item: dict, user_id: str) -> None:
        nonlocal changes
        if not item.get("user_id"):
            changes += 1
            if args.apply:
                store._update(
                    table,
                    lambda value: (
                        value.get("id") == item.get("id")
                        or value.get("token") == item.get("token")
                    ),
                    {"user_id": user_id},
                )

    agents = store.list_agents()
    for item in agents:
        update("agents", item, admin_id)
    agent_users = {item["id"]: item.get("user_id") or admin_id for item in agents}
    chats = store.list_chats()
    for item in chats:
        update("chats", item, agent_users.get(item.get("agent_id"), admin_id))
    chat_users = {item["id"]: item.get("user_id") or admin_id for item in chats}
    autopilots = store.list_autopilots()
    for item in autopilots:
        update("autopilots", item, agent_users.get(item.get("agent_id"), admin_id))
    autopilot_users = {
        item["id"]: item.get("user_id") or admin_id for item in autopilots
    }
    for item in store.list_all_autopilot_runs():
        update(
            "autopilot_runs",
            item,
            chat_users.get(
                item.get("chat_id"),
                autopilot_users.get(item.get("autopilot_id"), admin_id),
            ),
        )
    for item in store._all("shares"):
        update("shares", item, chat_users.get(item.get("chat_id"), admin_id))
    action = "Applied" if args.apply else "Would apply"
    print(f"{action} {changes} ownership updates in {data_dir / 'platform.sqlite3'}")
    if not args.apply:
        print("Re-run with --apply to write these changes.")


if __name__ == "__main__":
    main()
