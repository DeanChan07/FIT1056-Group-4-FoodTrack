"""Create demo data in data/foodshare.sqlite3.

Run: python seed.py          (refuses to overwrite existing data)
     python seed.py --reset  (deletes the database first)

Every date is worked out from today, so the demo always looks fresh.
Every demo password is: DemoPassword123!
"""

import os
import sys
from datetime import date, datetime, timedelta

from foodshare import data_path
from foodshare import domain as d
from foodshare.passwords import hash_password
from foodshare.storage import SqliteStore

PATH = data_path()
DEMO_PASSWORD = "DemoPassword123!"

USERS = [
    ("admin", "Ivy (IT Admin)", d.ADMIN),
    ("manager", "Mia (Manager)", d.MANAGER),
    ("staff", "Sam (Staff)", d.STAFF),
    ("volunteer", "Vic (Volunteer)", d.VOLUNTEER),
    ("recipient", "Rina", d.RECIPIENT),
    ("recipient2", "Ravi", d.RECIPIENT),
    ("recipient3", "Tom", d.RECIPIENT),
]


def _today_slot():
    """A pickup time later today (next quarter hour, at least 30 minutes away),
    so check-in can be tried straight away. None late at night."""
    soon = datetime.now() + timedelta(minutes=30)
    minutes = (soon.hour * 60 + soon.minute + 14) // 15 * 15
    return d.format_time(minutes) if minutes <= 23 * 60 + 45 and soon.date() == date.today() \
        else None


def seed(path=PATH, today_pickup="auto"):
    """today_pickup: "auto" picks a time later today, None leaves Tom out, or give "HH:MM"."""
    store = SqliteStore(path)
    today = date.today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    password_hash = hash_password(DEMO_PASSWORD)  # same demo password for everyone
    with store.transaction() as tx:
        if tx.count("users"):
            raise SystemExit(f"{path} already has data. Use --reset to start again.")
        ids = {}
        for username, name, role in USERS:
            ids[username] = tx.insert("users", {
                "username": username, "display_name": name, "role": role, "active": True,
                "password_hash": password_hash, "failed_logins": 0,
                "created_by": None, "created_at": now})["id"]
        tx.insert("profiles", {
            "recipient_id": ids["recipient"], "version": 1, "household_size": 4,
            "allergies": ["peanut"], "dietary_restrictions": [], "cultural_needs": ["halal"],
            "accessibility_needs": "Ground floor pickup", "preferred_pickup": "Afternoons",
            "urgency": "Soon", "updated_by": ids["recipient"], "updated_at": now})
        tx.insert("profiles", {
            "recipient_id": ids["recipient2"], "version": 1, "household_size": 1,
            "allergies": [], "dietary_restrictions": ["vegetarian"], "cultural_needs": [],
            "accessibility_needs": "", "preferred_pickup": "", "urgency": "Standard",
            "updated_by": ids["recipient2"], "updated_at": now})
        batches = [
            ("Rice 1kg", "Dry goods", 20, 200, [], ["halal", "vegetarian"]),
            ("Canned chickpeas", "Canned", 12, 300, [], ["halal", "vegetarian"]),
            ("Peanut butter", "Spreads", 8, 120, ["peanut"], ["halal", "vegetarian"]),
            ("Halal chicken", "Frozen", 6, 5, [], ["halal"]),
            ("Bread loaf", "Bakery", 4, 2, ["wheat"], ["vegetarian"]),
            ("Yoghurt", "Dairy", 10, -1, ["milk"], ["vegetarian"]),
        ]
        for name, cat, qty, days, allergens, tags in batches:
            batch = tx.insert("batches", {
                "name": name, "category": cat, "quantity": qty,
                "expiry_date": (today + timedelta(days=days)).isoformat(),
                "allergens": allergens, "dietary_tags": tags, "source_donation": None,
                "created_at": now, "on_hold": False, "version": 1})
            tx.insert("adjustments", {"batch_id": batch["id"], "change": qty,
                                      "reason": "New stock added", "made_by": ids["staff"],
                                      "made_at": now})
        tx.insert("donations", {
            "reference": "DN-DEMO01", "donor_name": "Local bakery",
            "dropoff_date": tomorrow, "dropoff_time": "09:30",
            "items": [{"item_type": "Wholemeal bread", "offered_qty": 10},
                      {"item_type": "Muffins", "offered_qty": 6}],
            "status": d.SCHEDULED, "created_at": now})
        tx.insert("tasks", {
            "volunteer_id": ids["volunteer"], "task_type": "Receiving",
            "shift_date": tomorrow, "shift_time": "09:00",
            "instructions": "Check donation DN-DEMO01 at the back door. Record accepted items.",
            "assigned_by": ids["manager"]})
        tx.insert("tasks", {
            "volunteer_id": ids["volunteer"], "task_type": "Distribution",
            "shift_date": today.isoformat(), "shift_time": "08:00",
            "instructions": "Help at the pickup desk today.", "assigned_by": ids["manager"]})
        tx.insert("allocations", {
            "recipient_id": ids["recipient"], "status": d.ALLOCATED,
            "pickup_date": tomorrow, "pickup_time": "14:00",
            "created_by": ids["staff"], "created_at": now,
            "items": [{"item_id": 1, "batch_id": 1, "name": "Rice 1kg", "quantity": 2},
                      {"item_id": 2, "batch_id": 4, "name": "Halal chicken", "quantity": 1}]})
        # Second Recipient booked at the same time, to show the pickup queue staggering.
        tx.insert("allocations", {
            "recipient_id": ids["recipient2"], "status": d.ALLOCATED,
            "pickup_date": tomorrow, "pickup_time": "14:00",
            "created_by": ids["staff"], "created_at": now,
            "items": [{"item_id": 1, "batch_id": 5, "name": "Bread loaf", "quantity": 1}]})
        slot = _today_slot() if today_pickup == "auto" else today_pickup
        if slot:  # Tom collects later today, so check-in and the live queue can be tried now
            tx.insert("allocations", {
                "recipient_id": ids["recipient3"], "status": d.ALLOCATED,
                "pickup_date": today.isoformat(), "pickup_time": slot,
                "created_by": ids["staff"], "created_at": now,
                "items": [{"item_id": 1, "batch_id": 2, "name": "Canned chickpeas",
                           "quantity": 2}]})
        for rating, category, message in [
            (5, "Staff and volunteers", "Everyone was so kind and nobody made me feel awkward."),
            (4, "Pickup and waiting", "Knowing my time window meant I didn't have to wait outside."),
            (3, "Food quality", "Could there be more fresh vegetables some weeks?"),
        ]:
            tx.insert("feedback", {"rating": rating, "category": category, "message": message,
                                   "submitted_on": today.isoformat(), "reviewed": False,
                                   "archived": False})
    return store


def remove_database(path=PATH):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        remove_database()
    seed()
    print(f"Demo data written to {PATH}. Every demo password is: {DEMO_PASSWORD}")
