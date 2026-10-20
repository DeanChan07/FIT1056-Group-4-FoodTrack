# How the review issues were handled

The "FoodShare Tracker: Flask vs Streamlit Review" compared the Flask + SQLite build
(Version 1) with the Streamlit + JSON build (Version 2) and listed 35 issues. This
release keeps the Streamlit screens from Version 2, moves the data to SQLite, and adds
the SRS v1.5 features that only Version 1 had. The table shows what happened to each issue.

Tests are in `tests/test_review_fixes.py` unless another file is named.

## Issues in the Streamlit version

| ID | Problem | What changed | Test |
|---|---|---|---|
| C3 | Built against SRS v1.3 | Added the v1.5 features: audit log, signed stock corrections and reversals, safety holds, IT Admin bootstrap and recovery, check-in queue with Serving / No-show, swap expiry and closure, feedback archive and 90-day removal, allocation cancellation | tests listed below |
| C4 | No way to cancel an allocation | `cancel_allocation` releases the reservation, closes waiting swaps, notifies the Recipient; needs a tick box and a reason | `test_c4_*`, `test_app.py::test_staff_cancel_a_pickup` |
| C5 | Volunteers could see every allocation and swap reasons | Volunteers see allocations only on the pickup day of their own Distribution shift; swaps are removed from what they receive | `test_c5_*` |
| C6 | Only reachable on localhost | `run.py --network --cert --key` serves the app over HTTPS to phones; localhost stays the safe default | manual (see README) |
| C7 | Weak sign-in | 15 to 128 character passwords, growing pause after 5 wrong passwords, 15-minute idle and 8-hour session limits, sign-ins audited | `test_c7_*`, `test_m15_*`, `test_sessions_*` |
| M6 | Past dates accepted | Donation drop-offs, pickups, rescheduling and task shifts refuse past dates and times | `test_m6_*` |
| M7 | Human checks never done | Still needs people. Recording sheet in `docs/USABILITY_SESSION_TEMPLATE.md` | — |
| M8 | Swaps never expire | Waiting requests become Expired when the pickup window ends; decisions after that are refused | `test_m8_*` |
| M9 | Collection marked swaps "Declined" | New Closed status with a clear message | `test_m9_*` |
| M10 | Any Distribution task authorised every collection | The Volunteer's Distribution shift must be on the collection day, which must be today | `test_m10_*`, `test_app.py::test_volunteer_records_todays_collection` |
| M11 | Collection date unvalidated, no field | "Collected on" date field for Staff; future dates and dates before the allocation are refused | `test_m11_*` |
| M12 | Alerts and reports used shelf stock | Low stock uses on shelf − set aside, leaving out expired and held food; expired items show as 0; report splits in-date and expired units | `test_m12_*`, `test_report_splits_expired_stock` |
| M13 | Quantity edited directly, no history | Editing a batch no longer changes quantity; corrections need a reason, respect reservations, keep history and can be reversed once | `test_m13_*`, `test_app.py::test_staff_correct_stock_and_undo_it` |
| M14 | JSON file, no backup | SQLite with one-writer transactions; `manage.py backup` and `restore` | `test_m14_*`, `test_concurrency.py` |
| M15 | Refresh signed you out | Server-side sessions with a cookie; refresh keeps you signed in, sign-out ends the session | `test_m15_*`, checked in a browser |
| N6 | Package bloat | `.venv`, caches, `.DS_Store`, the old Flask folder and data files are not in the repository (`.gitignore`) | — |
| N7 | Exactly Python 3.13.9 required | Any Python 3.11 or newer | — |
| N8 | README described data not shipped | No data is shipped; `seed.py` creates it with dates relative to today | `test_c1_*` |
| N9 | Leftover test data | As N8 | — |
| N10 | No limit on anonymous feedback | 5 per browser session, counted in memory only | `test_app.py::test_feedback_box_stops_after_five_in_one_session` |
| N11 | Drop-off time not validated | Checked as HH:MM like pickup times | `test_n11_*` |
| N12 | Typed names rendered as Markdown | `esc()` in `views/common.py` used wherever typed text is shown | `test_n12_*`, `test_app.py::test_typed_names_are_not_turned_into_links` |
| N13 | Two different stock totals | Dashboard and Inventory both use `usable_units` | `test_n13_*` |

## Issues in the Flask version, and how this build avoids them

| ID | Problem | In this build |
|---|---|---|
| C1 | README password failed on a fresh install | Setup always runs `seed.py`; the README password is the seeded one. `test_c1_*` signs in as every demo account on a fresh database |
| C2 | README claimed a database was shipped | The README says the database is created on first run |
| M1 | Too much code to explain | Services are split into eight feature modules (`foodshare/services/`), each small enough for one team member to own |
| M2 | Docs read like an assistant's work log | Docs rewritten; no assistant notes or cloud paths |
| M3 | Every request loaded the whole database | Pages query only the rows they need |
| M4 | Lockout could block staff | A growing pause capped at 15 minutes instead of a hard lock |
| M5 | Stale demo data | Demo data is always relative to today |
| N1, N2 | Raw timestamps; no expected time before check-in | Times are formatted; Recipients see their place and window before they leave home |
| N3 | Unstyled 404 | Unknown addresses show a "Page not found" message and open the home page |
| N4 | One-line root README | Root README describes the project |

## Known limits

- The sign-in cookie is written by the page, so it cannot be `HttpOnly`. The token is random, stored only as a hash, and expires after 15 idle minutes.
- `run.py --network` needs a certificate for HTTPS. For a class demo a self-signed certificate is fine; for real use, put the app behind a proper HTTPS host.
- The feedback box keeps the optional face rating and topic. Remove them if the team reads FR-45 to FR-47 as text only.
- NFR-02 (usability) and NFR-08 (grayscale and keyboard review) need people to run them.
