"""Looking after the database from the computer that runs the app.

    python manage.py backup [file]        copy the database (default: backups/<date-time>.sqlite3)
    python manage.py restore <file>       put a backup back (stop the app first)
    python manage.py create-admin         make the first IT Admin (only when none exists)
    python manage.py reset-admin          set a new password for an IT Admin
    python manage.py maintenance          remove anonymous feedback older than 90 days

These commands only work on this computer, never through the website, so nobody
on the network can use them to take over an account (FR-38, FR-40, NFR-04).
"""

import getpass
import os
import sqlite3
import sys
from datetime import datetime

from foodshare import APP_DIR, data_path
from foodshare import services as s
from foodshare.domain import DomainError
from foodshare.storage import SqliteStore


def _ask_password():
    first = getpass.getpass("New password (15 to 128 characters): ")
    if first != getpass.getpass("Type it again: "):
        sys.exit("The two passwords were different. Nothing was changed.")
    return first


def backup(target=None):
    target = target or os.path.join(
        APP_DIR, "backups", f"foodshare-{datetime.now():%Y%m%d-%H%M%S}.sqlite3")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    SqliteStore(data_path()).backup(target)
    print(f"Backup saved to {target}")
    return target


def restore(source):
    check = sqlite3.connect(source)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            sys.exit(f"{source} is damaged. Nothing was changed.")
        check.execute("SELECT COUNT(*) FROM users")
    except sqlite3.DatabaseError:
        sys.exit(f"{source} is not a FoodShare Tracker database. Nothing was changed.")
    finally:
        check.close()
    live = data_path()
    if os.path.exists(live):
        safety = backup()  # keep what was there, just in case
        print(f"(The data that was replaced is in {safety})")
    SqliteStore(live)  # make sure the live file exists
    source_conn, live_conn = sqlite3.connect(source), sqlite3.connect(live, timeout=30)
    try:
        source_conn.backup(live_conn)  # SQLite copies every page safely
    finally:
        live_conn.close()
        source_conn.close()
    print(f"Restored {source}. Start the app again with: python run.py")


def main(args):
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    command, rest = args[0], args[1:]
    try:
        if command == "backup":
            backup(rest[0] if rest else None)
        elif command == "restore" and rest:
            restore(rest[0])
        elif command == "create-admin":
            username = input("Username for the IT Admin: ")
            name = input("Display name: ")
            s.bootstrap_admin(SqliteStore(data_path()), username, _ask_password(), name)
            print("IT Admin created. Sign in at http://localhost:8501")
        elif command == "reset-admin":
            username = input("IT Admin username: ")
            s.recover_admin(SqliteStore(data_path()), username, _ask_password())
            print("Password changed. Every session that account had open has been ended.")
        elif command == "maintenance":
            removed = s.delete_old_feedback(SqliteStore(data_path()))
            print(f"Removed {removed} feedback message(s) older than 90 days.")
        else:
            print(__doc__)
            sys.exit(1)
    except DomainError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main(sys.argv[1:])
