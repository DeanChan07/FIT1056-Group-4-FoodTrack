"""SQLite storage (repository and transaction layer).

Each record type has its own table in one SQLite file (data/foodshare.sqlite3).
The services never write SQL themselves; they use a small ``Tx`` helper:

    with store.transaction() as tx:          # BEGIN IMMEDIATE (one writer at a time)
        batch = tx.get("batches", 1)         # SELECT ... WHERE id = ?
        batch["quantity"] -= 2               # change the dict like normal Python
    # leaving the block saves every changed row (UPDATE) and COMMITs.
    # An exception anywhere inside rolls everything back (NFR-03).

Only the rows a service asks for are loaded, so pages stay fast as the
data grows. Lists (allergens, allocation items ...) are stored as JSON text
in their column. The audit log and stock adjustment history are
append-only: database triggers refuse any UPDATE or DELETE (FR-42, FR-57).
"""

import copy
import json
import os
import sqlite3
from contextlib import contextmanager

SCHEMA_VERSION = 1

# table -> {column: kind}. kind is "int", "text", "bool" or "json". Every table also has "id".
TABLES = {
    "users": {
        "username": "text", "display_name": "text", "role": "text", "active": "bool",
        "password_hash": "text", "created_by": "int", "created_at": "text",
        "deactivation_verification": "json", "failed_logins": "int", "locked_until": "text",
    },
    "sessions": {
        "token_hash": "text", "user_id": "int", "created_at": "text", "last_seen": "text",
    },
    "profiles": {
        "recipient_id": "int", "version": "int", "household_size": "int",
        "allergies": "json", "dietary_restrictions": "json", "cultural_needs": "json",
        "accessibility_needs": "text", "preferred_pickup": "text", "urgency": "text",
        "updated_by": "int", "updated_at": "text",
    },
    "donations": {
        "reference": "text", "donor_name": "text", "dropoff_date": "text",
        "dropoff_time": "text", "items": "json", "status": "text", "created_at": "text",
        "received_by": "int", "received_at": "text", "receipt": "text",
    },
    "batches": {
        "name": "text", "category": "text", "quantity": "int", "expiry_date": "text",
        "allergens": "json", "dietary_tags": "json", "source_donation": "text",
        "created_at": "text", "on_hold": "bool", "hold_reason": "text", "version": "int",
    },
    "adjustments": {
        "batch_id": "int", "change": "int", "reason": "text", "made_by": "int",
        "made_at": "text", "reverses_id": "int",
    },
    "allocations": {
        "recipient_id": "int", "status": "text", "pickup_date": "text", "pickup_time": "text",
        "created_by": "int", "created_at": "text", "items": "json",
        "checked_in_at": "text", "queue_state": "text",
        "closed_by": "int", "closed_at": "text", "close_reason": "text",
    },
    "distributions": {
        "allocation_id": "int", "recipient_id": "int", "collected_date": "text",
        "items": "json", "recorded_by": "int",
    },
    "swaps": {
        "allocation_id": "int", "item_id": "int", "item_name": "text", "recipient_id": "int",
        "reason": "text", "status": "text", "response": "text", "replacement_batch_id": "int",
        "created_at": "text", "reviewed_by": "int", "closed_at": "text",
    },
    "tasks": {
        "volunteer_id": "int", "task_type": "text", "shift_date": "text", "shift_time": "text",
        "instructions": "text", "assigned_by": "int",
    },
    "notifications": {
        "user_id": "int", "kind": "text", "message": "text", "read": "bool",
        "created_at": "text",
    },
    "feedback": {
        "rating": "int", "category": "text", "message": "text", "submitted_on": "text",
        "reviewed": "bool", "archived": "bool",
    },
    "audit": {
        "at": "text", "actor_id": "int", "actor_role": "text", "category": "text",
        "action": "text", "target": "text", "details": "json",
    },
}

SQL_TYPES = {"int": "INTEGER", "text": "TEXT", "bool": "INTEGER", "json": "TEXT"}

EXTRA_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS users_username ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_token ON sessions(token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS profiles_recipient ON profiles(recipient_id);
CREATE UNIQUE INDEX IF NOT EXISTS donations_reference ON donations(reference);
CREATE UNIQUE INDEX IF NOT EXISTS distributions_allocation ON distributions(allocation_id);
CREATE UNIQUE INDEX IF NOT EXISTS adjustments_one_reversal ON adjustments(reverses_id);
CREATE INDEX IF NOT EXISTS allocations_status ON allocations(status, pickup_date);
CREATE INDEX IF NOT EXISTS swaps_allocation ON swaps(allocation_id, status);
CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id, read);
CREATE INDEX IF NOT EXISTS adjustments_batch ON adjustments(batch_id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
    BEGIN SELECT RAISE(ABORT, 'The audit log cannot be changed.'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
    BEGIN SELECT RAISE(ABORT, 'The audit log cannot be changed.'); END;
CREATE TRIGGER IF NOT EXISTS adjustments_no_update BEFORE UPDATE ON adjustments
    BEGIN SELECT RAISE(ABORT, 'Stock history cannot be changed. Add a reversal instead.'); END;
CREATE TRIGGER IF NOT EXISTS adjustments_no_delete BEFORE DELETE ON adjustments
    BEGIN SELECT RAISE(ABORT, 'Stock history cannot be changed. Add a reversal instead.'); END;
"""

DEFAULT_SETTINGS = {
    "low_stock_threshold": 5,
    "minutes_per_pickup": 6,
    "queue_window_minutes": 15,
    "queue_paused": False,
}


class SqliteStore:
    """Opens the SQLite file, creates the tables, and hands out transactions."""

    def __init__(self, path):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # readers never block the writer
            self._create_tables(conn)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _create_tables(conn):
        for table, columns in TABLES.items():
            cols = ", ".join(f'"{name}" {SQL_TYPES[kind]}' for name, kind in columns.items())
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" '
                         f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {cols})")
            # Older files: add any column that is missing, without losing rows (NFR-04).
            have = {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            for name, kind in columns.items():
                if name not in have:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {SQL_TYPES[kind]}')
        conn.executescript(EXTRA_SQL)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                         (key, json.dumps(value)))
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def reader(self):
        """A Tx for reading only. Changes made to its records are never saved."""
        return Tx(self._connect(), writable=False)

    @contextmanager
    def transaction(self):
        """Run the block as one database transaction: all of it is saved, or none of it."""
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")  # waits for any other writer, then holds the lock
        tx = Tx(conn, writable=True)
        try:
            yield tx
            tx.flush()
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def backup(self, target_path):
        """Copy the whole database to another file, safely, even while the app runs."""
        source = self._connect()
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    def dump(self):
        """Every row of every table as plain dicts (for tests and checks)."""
        tx = self.reader()
        data = {table: tx.all(table) for table in TABLES}
        data["settings"] = tx.settings()
        return data


class Tx:
    """Reads rows as dicts and remembers them, so changes can be saved at the end.

    The same row is always the same dict inside one Tx, so two parts of a service
    that load the same allocation see each other's changes."""

    def __init__(self, conn, writable):
        self.conn = conn
        self.writable = writable
        self._loaded = {}  # (table, id) -> [record, the JSON last written]

    # -------------------------------------------------- converting rows

    @staticmethod
    def _to_python(table, row):
        record = {"id": row["id"]}
        for name, kind in TABLES[table].items():
            value = row[name]
            if kind == "json":
                value = json.loads(value) if value is not None else None
            elif kind == "bool":
                value = bool(value) if value is not None else False
            record[name] = value
        return record

    @staticmethod
    def _to_sql(table, name, value):
        kind = TABLES[table][name]
        if kind == "json":
            return json.dumps(value) if value is not None else None
        if kind == "bool":
            return int(bool(value))
        return value

    def _remember(self, table, record):
        key = (table, record["id"])
        if key in self._loaded:  # keep the copy already being changed
            return self._loaded[key][0]
        self._loaded[key] = [record, json.dumps(record, sort_keys=True)]
        return record

    # -------------------------------------------------- saving

    def flush(self):
        """Write every remembered row that has changed since it was loaded."""
        if not self.writable:
            return
        for (table, record_id), entry in self._loaded.items():
            record, written = entry
            now = json.dumps(record, sort_keys=True)
            if now == written:
                continue
            unknown = set(record) - set(TABLES[table]) - {"id"}
            if unknown:
                raise ValueError(f"{table} has no column {', '.join(sorted(unknown))}")
            names = list(TABLES[table])
            self.conn.execute(
                f'UPDATE "{table}" SET ' + ", ".join(f'"{n}" = ?' for n in names) + " WHERE id = ?",
                [self._to_sql(table, n, record.get(n)) for n in names] + [record_id])
            entry[1] = now

    def _select(self, table, where="", params=()):
        self.flush()  # so queries see changes made earlier in this transaction
        rows = self.conn.execute(f'SELECT * FROM "{table}" {where} ORDER BY id', params)
        return [self._remember(table, self._to_python(table, row)) for row in rows]

    # -------------------------------------------------- the helpers services use

    def insert(self, table, record):
        if not self.writable:
            raise RuntimeError("Use store.transaction() to save changes.")
        unknown = set(record) - set(TABLES[table])
        if unknown:
            raise ValueError(f"{table} has no column {', '.join(sorted(unknown))}")
        names = list(record)
        if names:
            cursor = self.conn.execute(
                f'INSERT INTO "{table}" (' + ", ".join(f'"{n}"' for n in names) + ") VALUES ("
                + ", ".join("?" for _ in names) + ")",
                [self._to_sql(table, n, record[n]) for n in names])
        else:
            cursor = self.conn.execute(f'INSERT INTO "{table}" DEFAULT VALUES')
        full = {"id": cursor.lastrowid}
        for name, kind in TABLES[table].items():
            full[name] = record.get(name, False if kind == "bool" else None)
        return self._remember(table, full)

    def all(self, table):
        return self._select(table)

    def get(self, table, record_id):
        try:
            record_id = int(record_id)
        except (TypeError, ValueError):
            return None
        key = (table, record_id)
        if key in self._loaded:
            return self._loaded[key][0]
        rows = self._select(table, "WHERE id = ?", (record_id,))
        return rows[0] if rows else None

    def find(self, table, **criteria):
        for name in criteria:
            if name != "id" and TABLES[table].get(name) in (None, "json"):
                raise ValueError(f"Cannot search {table} by {name}")
        where = " AND ".join(f'"{n}" IS ?' for n in criteria)
        params = [criteria[n] if n == "id" else self._to_sql(table, n, criteria[n])
                  for n in criteria]
        return self._select(table, f"WHERE {where}" if where else "", params)

    def find_one(self, table, **criteria):
        matches = self.find(table, **criteria)
        return matches[0] if matches else None

    def count(self, table, **criteria):
        where = " AND ".join(f'"{n}" IS ?' for n in criteria)
        params = [self._to_sql(table, n, criteria[n]) for n in criteria]
        self.flush()
        return self.conn.execute(f'SELECT COUNT(*) FROM "{table}" '
                                 + (f"WHERE {where}" if where else ""), params).fetchone()[0]

    def settings(self):
        return {row["key"]: json.loads(row["value"])
                for row in self.conn.execute("SELECT key, value FROM settings")}

    def setting(self, key):
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else copy.deepcopy(DEFAULT_SETTINGS.get(key))

    def set_setting(self, key, value):
        if not self.writable:
            raise RuntimeError("Use store.transaction() to save changes.")
        self.conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                          (key, json.dumps(value)))
