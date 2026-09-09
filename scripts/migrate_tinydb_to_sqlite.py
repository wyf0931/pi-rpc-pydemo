"""Migrate platform.json to platform.sqlite3 with validation and backup."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.storage import migrate_tinydb, validate_tinydb_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--apply", action="store_true", help="Perform the migration; default is dry-run"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Fail on legacy orphan relations"
    )
    args = parser.parse_args()
    data_dir = args.data.expanduser()
    legacy = data_dir / "platform.json"
    sqlite = data_dir / "platform.sqlite3"
    if sqlite.exists():
        print(f"SQLite database already exists: {sqlite}")
        return
    if not legacy.exists():
        print(f"No legacy TinyDB file found: {legacy}")
        return
    counts = validate_tinydb_source(legacy, strict=args.strict)
    print(
        "Source table counts:",
        ", ".join(f"{key}={value}" for key, value in counts.items()),
    )
    if not args.apply:
        print(f"Validated migration source: {legacy}")
        print("Re-run with --apply to create SQLite and a timestamped backup.")
        return
    backup = migrate_tinydb(legacy, sqlite, strict=args.strict)
    print(f"Created {sqlite}")
    print(f"Backed up legacy data to {backup}")


if __name__ == "__main__":
    main()
