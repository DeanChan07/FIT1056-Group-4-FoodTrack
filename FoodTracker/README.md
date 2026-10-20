# FoodShare Tracker

A Python app for a single-site community food bank, built from the Team04 FIT1056 SRS (v1.5).
The screens are built with **Streamlit** and the data lives in a **SQLite** database (`data/foodshare.sqlite3`).

## Run it

Needs **Python 3.11 or newer** (https://www.python.org/downloads/).
The setup script builds a fresh `.venv`, installs Streamlit and pytest into it, and creates the demo data.

**macOS or Linux, from this folder:**
```bash
bash setup.sh
./.venv/bin/python run.py
```

**Windows (PowerShell), from this folder:**
```powershell
.\setup.ps1
.\.venv\Scripts\python.exe run.py
```

The app opens in your browser at http://localhost:8501. Press **Ctrl+C** in the Terminal window to stop it.

- If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` first, in the same window.
- If port 8501 is already in use, the app is already running in another Terminal window. Use that one, or press Ctrl+C there first.
- Refreshing the page keeps you signed in. You are signed out after 15 minutes without activity, or 8 hours in total.
- `python seed.py --reset` puts the demo data back to how it started. All demo dates are worked out from today.

Doing it by hand instead:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python.exe
.venv/bin/python seed.py
.venv/bin/python run.py
```

### Using it from phones (Recipients and donors)

By default only the computer running the app can open it. To let phones on the same network open it:

```bash
.venv/bin/python run.py --network --cert cert.pem --key key.pem
```

It prints the address to open on the phone. The certificate and key make it HTTPS, so passwords and needs details are encrypted on the way. `run.py --network` without them also works, but only use that on a network you trust, for testing. Never commit `.pem` files (they are in `.gitignore`).

## Demo accounts

Every demo password is `DemoPassword123!`.

| Username | Role | Menu |
|---|---|---|
| (signed out) | Anyone | Welcome, Sign in, Create an account, Donate food, Check a donation, Feedback |
| recipient, recipient2, recipient3 | Recipient | Home, My food, My swaps, My needs, Notices, Feedback |
| volunteer | Volunteer | Home, My tasks, Receive, Collections, Notices |
| staff | Organisation Staff | Dashboard, Receive, Inventory, Recipients, Allocations, Queue, Swaps, Tasks, Alerts, Reports, Feedback, Accounts, Notices |
| manager | Organisation Manager | Dashboard, Team, Tasks, Inventory, Alerts, Reports, Feedback, Audit log, Notices |
| admin | IT Admin | Dashboard, Accounts, Audit log, Notices |

Each role only sees its own menu, and every service checks the role again before it does anything (FR-03).

- **Rina** (`recipient`) and **Ravi** (`recipient2`) are both booked at 14:00 tomorrow, so Ravi's home page shows place #2 with an estimate of 14:06 to 14:21.
- **Tom** (`recipient3`) is booked later today, so you can try **check-in** straight away. (If you seed the data very late at night, Tom has no booking.)
- **Vic** (`volunteer`) has a Distribution shift today, so Collections shows Tom's pickup.
- Donors need no account: use **Donate food**, then **Check a donation** with the reference. `DN-DEMO01` is a donation you can receive as `staff` or `volunteer`.

Passwords must be 15 to 128 characters. After 5 wrong passwords in a row an account pauses for 1 minute, then 2, 4, 8, up to 15 minutes. It is a pause, not a permanent lock, so nobody can keep a Staff member out by guessing their username.

## Things to try

| Feature | Where |
|---|---|
| **Check-in queue** | Sign in as `recipient3`, press **I'm here: check in** on Home. As `staff`, open **Queue**, pick today, then **Start serving** or **Did not come**. The Recipient's card updates by itself every 20 seconds. |
| **Private food swap** | Sign in as `recipient`, open **My food**, press **Request a private swap**. Staff decide on **Swaps**. A request still waiting when the pickup window ends becomes **Expired**; one still waiting when the food is collected becomes **Closed**. |
| **Cancel a pickup** | As `staff`, **Allocations**, open one, **Cancel this pickup**. The food goes back on the shelf and the Recipient gets a notice. |
| **Stock corrections** | As `staff`, **Inventory**, **Correct stock**. Every change needs a reason, can't go below what is set aside, and can be undone once. Editing a batch never changes its quantity. |
| **Safety hold** | As `staff`, **Inventory**, **Edit a batch**, tick **On hold**. Held food can't be set aside, swapped in or handed out. |
| **Audit log** | `admin` sees sign-ins and account changes; `manager` sees stock, food and queue changes. Nobody can edit or delete entries. |
| **Anonymous feedback** | **Feedback** in the menu, no sign-in needed. Staff and Managers mark it Reviewed or Archived. |

## Looking after the data

```bash
python manage.py backup              # copy the database to backups/
python manage.py restore <file>      # put a backup back
python manage.py create-admin        # make the first IT Admin (only when none exists)
python manage.py reset-admin         # new password for an IT Admin; ends their sessions
python manage.py maintenance         # remove anonymous feedback older than 90 days
```

These only work on the computer running the app, never through the website (FR-38, FR-40, NFR-04).

## Run the tests

```bash
./.venv/bin/python -m pytest      # Windows: .\.venv\Scripts\python.exe -m pytest
```

There are 188 tests. Each one uses its own fresh database.

- `tests/test_services.py` is named after the SRS acceptance criteria (AC-01 to AC-50).
- `tests/test_review_fixes.py` has at least one test for each problem in the Flask vs Streamlit review (C1, C4, C5, C7, M6 to M15, N11 to N13), plus the SRS v1.5 features added here.
- `tests/test_app.py` opens every page for every role with Streamlit's test runner, checks team pages refuse the wrong role, and fills in the main forms.
- `tests/test_new_features.py` covers feedback, the queue and swap withdrawal.
- `tests/test_concurrency.py` checks that saves at the same moment never lose a change or oversell stock, and that a form opened before someone else's change is refused instead of undoing it.
- `tests/test_passwords.py` checks password hashing.

## Structure (matches SRS Section 8 layers)

| File | Layer | What it does |
|---|---|---|
| `app.py` | Presentation | Picks the menu for the signed-in role and runs the chosen page |
| `foodshare/views/` | Presentation | One file per area: `public` (signed out), `home`, `food` (allocations, swaps, queue), `stock` (receive, inventory, corrections, alerts), `people` (needs, recipients, accounts, tasks), `insights` (reports, feedback, audit log), `nav` (menus), `common` (sign-in, shared helpers and look) |
| `foodshare/services/` | Application services | One module per feature (see `services/__init__.py`); each function checks the role (FR-03) and saves in one transaction |
| `foodshare/domain.py` | Domain rules | Roles, statuses, expiry rules (FR-15, FR-16), allergy and diet suitability, sign-in limits |
| `foodshare/storage.py` | Repository and transaction | SQLite tables, transactions, backup |
| `foodshare/passwords.py` | Security | Password hashing with Python's built-in scrypt |
| `run.py`, `setup.sh`, `setup.ps1`, `seed.py`, `manage.py` | — | Start the app, one-command setup, demo data, backup and admin tools |

### How the SQLite database works

- One table per record type: `users`, `sessions`, `profiles`, `donations`, `batches`, `adjustments`, `allocations`, `distributions`, `swaps`, `tasks`, `notifications`, `feedback`, `audit`, plus `settings`.
- Every change runs inside `store.transaction()`, which is one SQLite transaction (`BEGIN IMMEDIATE ... COMMIT`). If any rule fails, `ROLLBACK` undoes all of it, so stock and distribution records never get out of step (NFR-03).
- Only one save runs at a time, even across several app windows, so two people can never both take the last tin (NFR-10). If two people edit the same batch or needs profile, the second save is stopped and the latest version is shown instead.
- Pages read only the rows they need, so they stay quick as the data grows.
- The audit log and stock history are append-only: database triggers refuse any change or deletion.
- Passwords and session tokens are stored only as hashes.
- Set `FOODSHARE_DB=/path/to/file.sqlite3` to use a different database file.

## Notes and differences from the SRS

- The SRS mentions SQLAlchemy; this build uses Python's built-in `sqlite3` module so there is one less library to learn. Only `storage.py` touches the database.
- The SRS describes web pages; this build uses Streamlit. The screens only call `foodshare/services`, so the rules are the same either way.
- Stock is **reserved** when allocated (the "Set aside" column), **subtracted** when collection is recorded, and **released** if the allocation is cancelled or marked "Did not come" (FR-23). A swap moves the reservation from the old batch to the new one in the same save (FR-36).
- Volunteers see an allocation only on its pickup day and only if they have a Distribution shift that day. They never see swap reasons or needs.
- The feedback box keeps the optional face rating and topic from the earlier build alongside the message. Neither identifies anyone. If the team reads the SRS as requiring text only, remove the two widgets in `views/public.py`.
- The sign-in cookie is set by the page, so it cannot be `HttpOnly` (Streamlit has no way to set server cookies). The token in it is random, stored only as a hash, and ends after 15 idle minutes.
- Still to do by people, not code: the five-person usability session (NFR-02) and the grayscale and keyboard review (NFR-08). See `docs/USABILITY_SESSION_TEMPLATE.md`.

See `docs/REVIEW_FIXES.md` for how each issue in the review was handled.
