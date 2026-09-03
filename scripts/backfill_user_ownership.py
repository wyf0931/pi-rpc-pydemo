"""One-off ownership backfill for existing TinyDB metadata.

Run without --apply first to inspect the plan. This script intentionally is
not called from application startup; ownership decisions for legacy records
are an operator action.
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.store import Store


def assign(table, doc_id: int, user_id: str, apply: bool) -> None:
    if apply:
        table.update({"user_id": user_id}, doc_ids=[doc_id])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Platform data directory")
    parser.add_argument("--apply", action="store_true", help="Write ownership changes")
    args = parser.parse_args()
    settings = get_settings()
    data_dir = (args.data or settings.data_dir).expanduser()
    store = Store(data_dir / "platform.json")
    admin = store.get_user_by_username("admin")
    if not admin:
        raise SystemExit("admin user not found; start the app once before backfilling")
    admin_id = admin["id"]
    changes = 0

    agents = store.agents.all()
    for agent in agents:
        if not agent.get("user_id"):
            assign(store.agents, agent.doc_id, admin_id, args.apply)
            changes += 1

    agent_users = {
        agent["id"]: agent.get("user_id", admin_id) for agent in store.agents.all()
    }
    chats = store.chats.all()
    for chat in chats:
        if not chat.get("user_id"):
            assign(
                store.chats,
                chat.doc_id,
                agent_users.get(chat.get("agent_id"), admin_id),
                args.apply,
            )
            changes += 1

    autopilots = store.autopilots.all()
    for autopilot in autopilots:
        if not autopilot.get("user_id"):
            assign(
                store.autopilots,
                autopilot.doc_id,
                agent_users.get(autopilot.get("agent_id"), admin_id),
                args.apply,
            )
            changes += 1

    chat_users = {
        chat["id"]: chat.get("user_id", admin_id) for chat in store.chats.all()
    }
    autopilot_users = {
        item["id"]: item.get("user_id", admin_id) for item in store.autopilots.all()
    }
    for run in store.autopilot_runs.all():
        if not run.get("user_id"):
            assign(
                store.autopilot_runs,
                run.doc_id,
                chat_users.get(
                    run.get("chat_id"),
                    autopilot_users.get(run.get("autopilot_id"), admin_id),
                ),
                args.apply,
            )
            changes += 1

    for share in store.shares.all():
        if not share.get("user_id"):
            assign(
                store.shares,
                share.doc_id,
                chat_users.get(share.get("chat_id"), admin_id),
                args.apply,
            )
            changes += 1

    action = "Applied" if args.apply else "Would apply"
    print(f"{action} {changes} ownership updates in {data_dir / 'platform.json'}")
    if not args.apply:
        print("Re-run with --apply to write these changes.")


if __name__ == "__main__":
    main()
