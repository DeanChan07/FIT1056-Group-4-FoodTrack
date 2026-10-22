# FoodShare Tracker

MA-Team 04's single-site food-bank application uses Streamlit 1.66.0, feature services, framework-independent domain rules and SQLite through `sqlite3`.

## Start

Use Python 3.11 or newer; this release is verified on Python 3.12/Linux. Installation scripts install dependencies only; administrator creation and demonstration mode are explicit actions.

```bash
bash setup.sh
.venv/bin/python manage.py create-admin
.venv/bin/python run.py
```

Windows PowerShell:

For detailed Windows instructions and troubleshooting, see [Windows 安装与 VS Code 设置](#windows-安装与-vs-code-设置).

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe manage.py create-admin
.\.venv\Scripts\python.exe run.py
```

Open http://localhost:8501. The local bootstrap prompts for the first administrator's credentials. An IT Admin creates Managers; a Manager creates Staff and Volunteers. The first administrator can create another administrator only after entering their current password and confirming the action. Deactivating the last active administrator is rejected.

For the classroom demonstration:

```bash
.venv/bin/python run.py --demo
```

`--demo` (or `FOODSHARE_DEMO=1`) explicitly enables synthetic accounts, uses `data/demo.sqlite3` by default and shows demonstration credentials on the sign-in page. Normal mode uses `data/foodshare.sqlite3`, never auto-seeds privileged accounts and hides the demonstration panel. Do not reuse a previous classroom database for real operation. `FOODSHARE_DB` overrides the database path when an isolated/custom database is needed.

For other devices, provide a valid HTTPS certificate/key:

```bash
.venv/bin/python run.py --network --cert C.pem --key K.pem
```

HTTP network mode is refused. Use `run.py`: its supported `st.App` routes set the login cookie through a same-origin, CSRF-protected single-use handoff with HttpOnly and SameSite=Strict; HTTPS also adds Secure. A direct `streamlit run app.py` launch has tab-only authentication and no persistent login-cookie handoff.

## Windows 安装与 VS Code 设置

### 1. 打开正确文件夹和终端

解压项目后，进入包含 `setup.ps1`、`run.py` 和 `requirements.txt` 的 **FoodTracker** 文件夹。在 VS Code 中右键该文件夹，选择 **Open in Integrated Terminal**。确认终端当前位置以 `\FoodTracker` 结尾。

以下命令使用 **PowerShell**。提示符应为 `PS D:\...\FoodTracker>`；如果显示 `MINGW64` 或 `bash`，在当前终端输入 `powershell.exe` 后按 Enter。不要在 Git Bash 中直接运行 `setup.ps1`，否则会出现 `Set-Location: command not found` 等错误。

**每次只执行一条命令，等待重新出现 `PS ...>` 提示符后再执行下一条。** 不要复制提示符本身。若出现 `>>` 且无法继续，可按 Ctrl+C 返回提示符，再重新输入完整命令。

### 2. 检查 Python

```powershell
py -0p
```

此命令列出 Windows Python Launcher 找到的解释器及其路径。也可检查默认 `python` 命令：

```powershell
python --version
```

项目要求 Python 3.11 或以上。已有自动测试证据来自 Python 3.12/Linux；Windows/Python 3.14 的安装与测试结果需以实际执行为准。如果没有合适版本，请从 https://www.python.org/downloads/windows/ 安装，并勾选 `Add python.exe to PATH`，随后重新打开终端。

### 3. 安装依赖

如果运行脚本时提示 `running scripts is disabled on this system`，先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

若询问确认，输入 `Y` 后按 Enter。该设置只影响当前 PowerShell 进程，关闭终端后失效。然后执行：

```powershell
.\setup.ps1
```

显示 `Ready.` 表示脚本安装完成。**安装完成后不要重复运行该脚本：它会重新创建 `.venv`。**

如果出现 `py.exe: No suitable Python runtime found`，可能是脚本在探测未安装的 Python 版本时提前停止；这并不表示电脑完全没有 Python。当前脚本在部分 Windows PowerShell 环境中有此问题，可改用下面的手动安装流程。

以下以 `py -0p` 已列出的 **Python 3.14** 为例；如果已安装的是 3.12 或 3.13，请把第一条命令的 `-3.14` 换成对应版本。不要填写未安装的版本。

```powershell
py -3.14 -m venv .venv
```

检查虚拟环境是否成功创建：

```powershell
Test-Path .\.venv\Scripts\python.exe
```

应显示 `True`。若为 `False`，先处理创建虚拟环境时的错误，不要继续安装。若 `py` 不可用，但 `python --version` 确认是合适的 Windows Python，也可用 `python -m venv .venv` 创建后重新检查。

创建成功后，逐条执行：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

升级中出现 `Successfully uninstalled pip-...` 属正常步骤；等待最终的 `Successfully installed ...` 和 PowerShell 提示符。依赖安装也可能显示 `Requirement already satisfied`，表示已安装。若出现 `ERROR`，保留完整错误，先解决再继续。

### 4. 选择 VS Code 解释器

依赖装进 `.venv` 后，VS Code 可能仍选择全局 Python 或 `C:\msys64\mingw64\bin\python.exe`，导致 `import streamlit` 下方出现黄色波浪线。

1. 按 **Ctrl+Shift+P**，选择 **Python: Select Interpreter**。
2. 选择当前 FoodTracker 的 `.venv\Scripts\python.exe`。
3. 若列表没有，选择 **Enter interpreter path… → Find…**，手动找到 **FoodTracker → .venv → Scripts → python.exe**。
4. 等待分析完成；若黄线仍在，执行 **Developer: Reload Window**。如果没有解释器选择命令，请先在 VS Code 安装 Microsoft 的 Python 扩展。

可在 PowerShell 验证实际安装：

```powershell
.\.venv\Scripts\python.exe -c "import streamlit; print(streamlit.__version__)"
```

预期显示 `1.66.0`。选择解释器与终端中普通 `python` 命令的解析不一定同步；以下命令始终显式使用项目的虚拟环境，无需额外激活。

### 5. 运行 Pytest

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前发布版本的预期用例数为 **306**；以本机最终输出为准。全部通过时应显示 `306 passed`。若有 `FAILED` 或 `ERROR`，保存完整失败详情，不能把该次执行记为通过。保存终端截图，并记录以下命令输出的 Python 版本：

```powershell
.\.venv\Scripts\python.exe --version
```

### 6. 启动 Demo

测试通过后执行：

```powershell
.\.venv\Scripts\python.exe run.py --demo
```

保持终端打开，在浏览器访问 http://localhost:8501，使用登录页显示的 Demo 账号。Demo 默认使用独立的 `data/demo.sqlite3`；若已设置 `FOODSHARE_DB`，则使用该变量指定的数据库。Demo 不需要先执行 `create-admin`。停止服务时，在终端按 **Ctrl+C**。

以后启动 Demo，只需进入 FoodTracker 并运行上述启动命令，无需重复安装。正式使用时，先执行 `.\.venv\Scripts\python.exe manage.py create-admin`，再执行 `.\.venv\Scripts\python.exe run.py`，具体账号规则见前文。

## Tests and evidence

```bash
.venv/bin/python -m pytest
.venv/bin/python tools/verify_release.py
```

Run in the Malaysia deployment timezone. The application uses Asia/Kuala_Lumpur as its site clock. `docs/evidence/validation.json`, `pytest-output.txt` and `pytest-results.xml` contain the authoritative final count, versions, command, source hashes and individual cases. Parametrized cases count separately; the count is not a percentage of requirements or code coverage.

The requirement reference and non-functional evidence boundaries are included below. [Implementation diagrams](docs/diagrams/CURRENT_IMPLEMENTATION.md) describe the architecture, record relationships and four sequences. The database schema is in `docs/diagrams/sqlite-record-schema.json`.

## Operational rules

- Staff manually allocate suitable food. Known allergy/diet conflicts and unconfirmed allergy/allergen information block allocation and collection. Common allergen aliases are normalized. Staff must inspect actual labels; the software cannot infer undeclared allergens.
- Allocation reserves stock; collection deducts actual issued units once, creates stock history and one distribution, and closes active queue entries and swaps atomically. Receipt, adjustment and distribution history is append-only.
- Late pickup remains possible on its booked day. After its exclusive window end, only Staff may check in or record collection with an exception reason. The reason does not bypass food safety, account checks, inventory or duplicate-collection protection. An already-collected allocation cannot be collected again.
- From the following day, after the window has ended, a missed allocation becomes Expired and releases its reservation. A window crossing midnight remains valid until its actual end. Expired/cancelled pickups need a new allocation; they cannot be revived by an exception reason.
- Deactivating a Recipient cancels their uncompleted allocations, releases stock, closes pending swaps and queue entries, removes their notices and revokes sessions. Verification is recorded as a flag/actor/date without keeping the verification narrative.
- Receiving and Distribution permissions require an active task of the corresponding type on that day. Tasks can be edited with a version check or cancelled with confirmation. Cancellation revokes that task's authority immediately while preserving history.
- Queue order uses server check-in time and queue-entry ID. Only arrived Waiting/Serving people count ahead. A Waiting Recipient sees approximate `a*5` to `(a+1)*5` minutes by default; service duration is configurable. Serving/paused/unarrived states show no waiting estimate. Automatic fragments do not renew an idle session.
- Feedback requires 1-500 trimmed Unicode characters and stores only message/date/review flags plus its ID. Tokens stay in memory, forms are single-use and at most five successes are allowed per anonymous browser token in ten minutes. New tabs reuse a short-lived anonymous cookie where available. There is no account/IP link.
- Shared site-wide public caps protect donation booking (60/10 minutes), status lookup (300/10 minutes), registration (30/10 minutes) and feedback (120/10 minutes). They are conservative prototype caps, not per-person quotas, and can affect legitimate users during busy periods.
- Maintenance runs on application activity: overdue pickups are checked each run; retention checks are gated to once per hour. `python manage.py maintenance` forces cleanup. It deletes feedback older than 90 calendar days and invalid sessions. If the app is idle, cleanup waits for the next app activity or an external scheduled invocation.

## Backup, upgrade and recovery

```bash
.venv/bin/python manage.py backup
.venv/bin/python manage.py maintenance
.venv/bin/python manage.py reset-admin
```

Stop app writers before running `python manage.py restore <backup.sqlite3>`. A restore checks file existence, schema, integrity and stored JSON before replacing the live data, and creates a safety backup. Local admin recovery resets an existing active administrator and revokes sessions; the operator must verify organizational authority before using it.

Schema v2 is additive except for removal of the earlier feedback rating/category columns. Before upgrading a v1 database, `<database>.pre-v2.sqlite3` is created; a failed migration automatically restores that backup. Existing messages, dates, review flags and all records remain. Old allergen/allergy data is marked unconfirmed until checked. The pre-v2 backup retains the old schema and is intended for rollback with the previous application release, not the v2 restore command. Test an upgrade on a copy and pause app writers first. Current-version backup/restore and injected migration-failure recovery have automated examples; recovery on the team's real dataset still needs measurement.

## Structure and limitations

`views/` contains Streamlit widgets and display code; `services/` enforces authorization, current-state validation and transactions; `domain.py` contains pure rules; `storage.py` owns SQL, migrations, snapshots and backup/restore; `http_security.py` supplies the cookie handoff routes. SQL does not live in the views. Quantities reserved are derived from stored allocation items within one SQLite snapshot.

No real Staff usability sessions, Windows installation, browser keyboard/grayscale inspection, full browser-cookie lifecycle, HTTPS deployment verification, request-log privacy inspection or specified five-user performance baseline was performed here. AppTest is a headless UI harness, not a real browser. These remain separate SRS acceptance activities. Sensitive needs are plaintext in SQLite; POSIX file permissions are restricted, while disk encryption and Windows ACLs remain deployment responsibilities. Single-process anonymous token memory is appropriate to this one-server prototype; multiple workers would require redesigned anonymous token coordination.

The ZIP contains no live database, real credentials, virtual environment, caches or Git history. 

## Final automated result

306 passed, 0 failed, 0 errors, 0 skipped (116.94 seconds), completed 2026-10-22 09:28 MYT. This is an automated case count, not blanket SRS/NFR acceptance. Source manifest: `52f1ee29ed03688e3960262a153bc08a04b94035c3799c9f3cb66871ba901a6c`.

## Functional requirement reference

The following maps FR-01 through FR-57 to implemented behavior and representative automated examples. It is an evidence index, not a claim that every acceptance clause or deployment condition has been certified. Test functions are located under `tests/`; parametrized functions represent multiple cases.

| Requirement | Implemented behavior | Service/view | Representative pytest function |
|---|---|---|---|
| FR-01 | Recipient-only registration | `accounts` | `test_services.py::test_ac01_self_registration_creates_recipient` |
| FR-02 | Authentication and sign-out | `accounts` | `test_app.py::test_sign_in` |
| FR-03 | Role, ownership and task permissions | `base / accounts / people` | `test_app.py::test_team_pages_refuse_a_recipient` |
| FR-04 | Manager manages Staff and Volunteers | `accounts` | `test_app.py::test_manager_creates_a_volunteer` |
| FR-05 | Admin manages Managers | `accounts` | `test_services.py::test_ac06_admin_creates_manager_only` |
| FR-06 | Confirmation before deactivation | `accounts` | `test_services.py::test_ac05_manager_deactivates_volunteer_after_confirmation` |
| FR-07 | Verified Recipient deactivation, session and reservation revocation | `accounts` | `test_final_regressions.py::test_deactivation_cancels_reservations_swaps_notices_and_sessions` |
| FR-08 | Account-free donation booking | `donations` | `test_services.py::test_ac08_to_ac10_schedule_and_unique_reference` |
| FR-09 | Unique unpredictable donation reference | `donations` | `test_final_regressions.py::test_donation_references_are_long_unpredictable_tokens` |
| FR-10 | Assigned Volunteer / Staff receiving | `donations / people` | `test_final_regressions.py::test_cancelled_task_removes_receiving_and_distribution_authority` |
| FR-11 | Saved receipt confirmation | `donations` | `test_services.py::test_ac11_ac12_receive_adds_only_accepted` |
| FR-12 | Accepted stock and receipt history saved once, atomically | `donations` | `test_final_regressions.py::test_failed_receipt_rolls_back_batch_and_history` |
| FR-13 | Add/search/edit stock, restricted edits and archive | `stock` | `test_app.py::test_staff_add_stock` |
| FR-14 | On-hand, reserved and available invariants | `stock / allocations` | `test_submission_review.py::test_fifty_rounds_of_two_connection_stock_collection_and_swap_contention` |
| FR-15 | Inclusive seven-day near-expiry threshold | `domain / stock` | `test_services.py::test_ac15_ac16_near_expiry_boundary` |
| FR-16 | Expired/held food blocked, reservation shown and refusal audited | `stock / allocations` | `test_final_regressions.py::test_unsafe_block_is_audited_after_business_rollback` |
| FR-17 | Own needs profile / Staff consent and stale-form protection | `people` | `test_services.py::test_ac19_staff_needs_permission` |
| FR-18 | Required/optional fields and purpose guidance | `views.people / domain` | `test_final_views.py::test_profile_fields_explain_required_optional_and_purpose` |
| FR-19 | Minimal allocation needs summary | `people / domain` | `test_final_regressions.py::test_needs_summary_minimizes_private_fields_without_ranking` |
| FR-20 | Safe manual allocation, stock reservation and current needs validation | `allocations` | `test_submission_review.py::test_allocation_safety_decisions_change_independently` |
| FR-21 | Need indicators with no automatic Recipient ranking | `people` | `test_final_regressions.py::test_needs_summary_minimizes_private_fields_without_ranking` |
| FR-22 | Actual quantity/date collection and duplicate rejection | `allocations` | `test_final_regressions.py::test_late_staff_exception_still_allows_only_one_collection` |
| FR-23 | Atomic stock deduction, distribution, partial release and cancellation | `allocations` | `test_review_fixes.py::test_partial_collection_puts_the_rest_back` |
| FR-24 | Assign Volunteer shift; audited update/cancellation extension | `people` | `test_final_regressions.py::test_task_edit_conflict_permissions_and_cancellation` |
| FR-25 | Volunteer sees own task details | `people / views.people` | `test_app.py::test_volunteer_sees_only_their_tasks` |
| FR-26 | One unread pickup-change notice in the schedule transaction | `allocations` | `test_final_regressions.py::test_pickup_notice_is_atomic_and_noop_change_does_not_duplicate_it` |
| FR-27 | Near-expiry and per-item available-stock thresholds | `stock` | `test_final_regressions.py::test_individual_item_thresholds_and_held_report_stock` |
| FR-28 | Date-range reports and current stock status | `insights` | `test_services.py::test_ac39_bad_range_and_ac42_volunteer_denied` |
| FR-29 | Same report data/totals exported with safe CSV text | `insights` | `test_final_regressions.py::test_csv_neutralizes_formula_text_without_changing_numeric_cells` |
| FR-30 | Recipient previews own allocation | `allocations / views.food` | `test_app.py::test_recipient_asks_for_a_private_swap` |
| FR-31 | Optional reason; uncollected own-item request within window | `swaps` | `test_services.py::test_ac44_to_ac46_swap_request_rules` |
| FR-32 | One active swap per item | `swaps` | `test_services.py::test_ac44_to_ac46_swap_request_rules` |
| FR-33 | Pending status persisted and visible | `swaps` | `test_app.py::test_recipient_asks_for_a_private_swap` |
| FR-34 | Private reason restricted to Staff and owning Recipient | `swaps` | `test_services.py::test_ac47_volunteer_cannot_see_reason` |
| FR-35 | Current safe replacement and chosen quantity | `swaps / allocations` | `test_final_regressions.py::test_swap_replacement_quantity_and_stale_version` |
| FR-36 | Atomic reservation transfer; physical stock unchanged | `swaps` | `test_services.py::test_ac48_ac49_approve_swap` |
| FR-37 | Declined outcome and response visible to owner | `swaps` | `test_services.py::test_ac50_decline_visible_to_recipient` |
| FR-38 | Local first-admin bootstrap | `accounts / manage` | `test_review_fixes.py::test_admin_bootstrap_only_when_there_is_no_admin` |
| FR-39 | Admin management with reauthentication, confirmation and last-admin guard | `accounts / views.people` | `test_final_regressions.py::test_admin_management_requires_reauthentication_and_keeps_last_admin` |
| FR-40 | Local recovery of active Admin and session revocation | `accounts / manage` | `test_review_fixes.py::test_admin_recovery_resets_the_pause_and_ends_old_sessions` |
| FR-41 | Signed correction with reason code, before/after and actor | `stock` | `test_final_regressions.py::test_stock_correction_has_before_after_reason_code_and_source` |
| FR-42 | Linked source corrections and one reversing entry | `stock` | `test_final_regressions.py::test_stock_correction_has_before_after_reason_code_and_source` |
| FR-43 | Expired / Closed / Cancelled swap lifecycle before reads and decisions | `swaps` | `test_final_regressions.py::test_late_collection_closes_expired_swap_as_expired_not_closed` |
| FR-44 | Current Pending request/version and concurrent decision protection | `swaps` | `test_submission_review.py::test_fifty_rounds_of_two_connection_stock_collection_and_swap_contention` |
| FR-45 | Public feedback available while signed in under every role | `views.public / nav` | `test_app.py::test_every_menu_page_opens_for_its_role` |
| FR-46 | Trimmed 1-500 Unicode characters; escaped rendering | `insights / views.public` | `test_final_regressions.py::test_feedback_unicode_boundaries` |
| FR-47 | Feedback stores no submitter/account/network identifiers | `insights / storage` | `test_final_regressions.py::test_feedback_replay_rate_window_and_exact_storage_schema` |
| FR-48 | Private Staff/Manager feedback review and archive | `insights` | `test_new_features.py::test_feedback_inbox_is_staff_and_manager_only` |
| FR-49 | Single-use transient forms, rolling ten-minute cap and retention | `public_controls / maintenance` | `test_final_regressions.py::test_feedback_replay_rate_window_and_exact_storage_schema` |
| FR-50 | Assigned Volunteer / Staff check-in; idempotent active entry | `queue` | `test_final_regressions.py::test_queue_wait_formula_and_volunteer_transitions` |
| FR-51 | Arrival time + queue-entry ID order; role-controlled transitions | `queue` | `test_final_regressions.py::test_queue_ties_use_checkin_entry_id_not_allocation_id` |
| FR-52 | Private own queue response and last-updated time | `queue` | `test_final_regressions.py::test_queue_wait_formula_and_volunteer_transitions` |
| FR-53 | Approximate a*m to (a+1)*m wait; default m=5 | `queue` | `test_final_regressions.py::test_queue_wait_formula_and_volunteer_transitions` |
| FR-54 | 20-second fragments; failed refresh retains last confirmed time | `views.common / views.food` | `test_final_views.py::test_queue_failure_keeps_last_confirmed_timestamp` |
| FR-55 | Timing/pause configuration, no closed-window admission except documented Staff extension | `queue / allocations` | `test_final_regressions.py::test_queue_wait_formula_and_volunteer_transitions` |
| FR-56 | Redacted successful/denied audit events and lifecycle logging | `base / all services` | `test_final_regressions.py::test_unsafe_block_is_audited_after_business_rollback` |
| FR-57 | Role-separated append-only audit and unlinked feedback review | `insights / storage` | `test_submission_review.py::test_feedback_review_audit_has_no_feedback_link` |

## Non-functional verification status

| Requirement | Current technical evidence | Remaining acceptance work |
|---|---|---|
| NFR-01 | Service role/ownership/task denials; all menu pages exercised; expired/inactive session denials | Review full deployment permission matrix, including real browser endpoints |
| NFR-02 | Runnable application and task template | Five first-time Staff sessions, training limit and at least 4/5 independent completion: **not run** |
| NFR-03 | Transaction rollback, injected receipt/history/notice failures, no partial distribution, contention assertions | Fault injection at every save boundary is not claimed |
| NFR-04 | v1 preservation fixture, automatic pre-upgrade backup, forced migration failure restoring old records, current backup/restore | Rehearse on the team's complete real dataset; independently time recovery against the 30-minute target |
| NFR-05 | Read-only session validation, indexed navigation counts, reduced dashboard scans and date-filtered report queries | Specified 1,000-record / five-user / 100-operation / p95 <=2s browser/server baseline: **not run** |
| NFR-06 | Feature modules, concise rule/transaction comments, updated public interfaces, source manifest, tests and current diagrams | Team peer review and contribution sign-off |
| NFR-07 | Plain guidance, optional private swap reasons and escaped text | Full human dignity/plain-language review and participant understanding |
| NFR-08 | Visible text statuses including unknown allergens, paused queue, expired and denied states | Browser keyboard, focus, grayscale and assistive-technology inspection |
| NFR-09 | 15-128-character passwords, salted scrypt, five failures/15 minutes -> fixed 15-minute delay; 15-minute idle and eight-hour absolute sessions; passive-refresh checks | Browser persistence/logout/recovery under real HTTPS deployment |
| NFR-10 | 50 rounds x three two-connection races, stock invariants/report reconciliation; additional late-collection/replay races | No proof of all possible interleavings or whole-system load behavior |
| NFR-11 | Minimal feedback schema; no account/IP/token persisted with feedback; no submission-linked audit; usage analytics disabled | Inspect actual deployment access/proxy/network logs and browser requests; voluntary identifying free text remains possible |
| NFR-12 | Private queue projection; 20-second fragments; simulated failure retains last confirmed timestamp; idle Staff/Recipient refresh tests | Measure real browser refresh and offline/reconnect behavior under the NFR-05 load |
| NFR-13 | Append-only audit, Denied result for unsafe blocks, role separation, same-origin CSRF-protected HttpOnly cookie handoff, one-use exchange; non-loopback launcher requires HTTPS | Real certificate/browser cookie lifecycle and tampered Streamlit WebSocket/CSRF network tests; full operational audit review |
