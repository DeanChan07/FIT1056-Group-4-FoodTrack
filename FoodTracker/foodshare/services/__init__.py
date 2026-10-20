"""Application services: one function per use-case step, grouped by feature.

Every service checks the actor's role first (FR-03), applies the domain rules,
and makes its changes inside one storage transaction (NFR-03). The screens only
ever call these functions, as ``from foodshare import services as s``.

| Module         | Feature                                                   |
|----------------|-----------------------------------------------------------|
| accounts.py    | F-01 accounts, sign-in, sessions, IT Admin recovery       |
| donations.py   | F-02 donations                                            |
| stock.py       | F-03 inventory, holds, stock corrections, alerts          |
| people.py      | F-04 needs profiles, F-06 volunteer tasks                 |
| allocations.py | F-05 allocation and collection, F-07 notices              |
| swaps.py       | F-09 private swaps                                        |
| queue.py       | Pickup queue and check-in                                 |
| insights.py    | F-08 reports, anonymous feedback, audit log, dashboard    |
"""

from .accounts import (bootstrap_admin, create_internal_account, deactivate_account,
                       end_session, get_user, list_accounts, login, recover_admin,
                       register_recipient, resume_session, start_session, update_account)
from .allocations import (cancel_allocation, create_allocation, get_allocation,
                          list_allocations, list_notifications, mark_notifications_read,
                          record_collection, suitable_batches, unread_count, update_pickup)
from .base import require
from .donations import find_donation, list_donations, receive_donation, schedule_donation
from .insights import (audit_events, build_report, dashboard_stats, delete_old_feedback,
                       feedback_inbox, mark_feedback_reviewed, report_csv, submit_feedback)
from .people import (assign_task, get_profile, list_tasks, list_volunteers,
                     recipients_for_allocation, save_profile)
from .queue import check_in, move_in_queue, pickup_queue, queue_status, set_queue_settings
from .stock import (adjust_stock, get_batch, list_batches, reverse_adjustment, save_batch,
                    set_low_stock_threshold, stock_alerts, stock_history, usable_units)
from .swaps import (approve_swap, decline_swap, get_swap, list_swaps, refresh_swap_lifecycle,
                    request_swap, withdraw_swap)
