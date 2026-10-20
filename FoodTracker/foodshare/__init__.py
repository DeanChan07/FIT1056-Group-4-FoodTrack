"""FoodShare Tracker: a single-site community food bank prototype."""

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path():
    """The SQLite database file. Set FOODSHARE_DB to use a different one."""
    return os.environ.get("FOODSHARE_DB",
                          os.path.join(APP_DIR, "data", "foodshare.sqlite3"))
