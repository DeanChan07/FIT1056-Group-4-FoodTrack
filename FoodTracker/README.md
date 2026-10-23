# FoodShare Tracker

## Description

FoodShare Tracker is MA-Team 04's single-site food-bank application for FIT1056. It uses a Streamlit interface and SQLite to manage donations, inventory, recipient needs, food allocations, collection, volunteer tasks, private swap requests, anonymous feedback, and reports.

Business rules and permissions are checked in the service layer. Related inventory and collection changes are saved in database transactions. The application uses **Asia/Kuala_Lumpur** as its site timezone.

This README belongs inside the **FoodTracker** folder, alongside `run.py` and `requirements.txt`.

## Contents

- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [First-Time Installation: Windows PowerShell](#first-time-installation-windows-powershell)
- [VS Code Interpreter](#vs-code-interpreter)
- [Optional Virtual Environment Activation](#optional-virtual-environment-activation)
- [macOS and Linux Installation](#macos-and-linux-installation)
- [Windows Git Bash](#windows-git-bash)
- [Starting the App After Installation](#starting-the-app-after-installation)
- [Demo and Normal Operation](#demo-and-normal-operation)
- [Features and Business Rules](#features-and-business-rules)
- [Automated Tests](#automated-tests)
- [Manual Testing](#manual-testing)
- [Data, Backup, and Recovery](#data-backup-and-recovery)
- [Access From Other Computers](#access-from-other-computers)
- [Troubleshooting](#troubleshooting)
- [Architecture and Verification Limits](#architecture-and-verification-limits)
- [Functional Requirement Reference](#functional-requirement-reference)
- [Non-Functional Evidence Reference](#non-functional-evidence-reference)

## Project Structure

| File or folder | Purpose |
| --- | --- |
| `run.py` | Starts the server, selects Demo/network mode, and registers the login-cookie routes. |
| `app.py` | Configures the Streamlit interface and navigation. |
| `manage.py` | Creates or recovers administrators, backs up/restores the database, and runs maintenance. |
| `seed.py` | Creates synthetic demonstration data. |
| `requirements.txt` | Lists the pinned application and test dependencies. |
| `setup.ps1` | Installs Windows dependencies, reusing a valid local `.venv` unless recreation is requested. |
| `foodshare/views/` | Contains pages, forms, navigation, and display code. |
| `foodshare/services/` | Checks permissions and current records, and performs business transactions. |
| `foodshare/domain.py` | Contains framework-independent validation and business rules. |
| `foodshare/storage.py` | Handles SQLite persistence, migrations, and backup/restore. |
| `foodshare/passwords.py` | Hashes and verifies passwords. |
| `foodshare/http_security.py` | Handles the same-origin login-cookie exchange. |
| `.streamlit/config.toml` | Contains Streamlit settings. |
| `tests/` | Contains pytest tests, including concurrency and Streamlit AppTest cases. |
| `tools/verify_release.py` | Runs the tests and writes reproducible evidence. |
| `docs/evidence/` | Contains saved automated test results and environment information. |
| `docs/diagrams/` | Contains implementation diagrams and the database record schema. |
| `docs/USABILITY_SESSION_TEMPLATE.md` | Provides a template for recording usability sessions. |
| `data/` | Holds generated SQLite databases; created when needed. |
| `backups/` | Holds database backups when the default backup destination is used. |
| `.venv/` | Local Python environment created during installation; do not distribute it. |

## Requirements

- **Python 3.11 or newer.** The submitted Windows evidence records Python **3.14.2**, Streamlit **1.66.0**, pytest **9.1.1** and tzdata **2026.2**. A separate verification run for this prepared release is saved in `docs/evidence/validation.json`. Verify your own environment locally.
- An internet connection for the initial dependency download.
- A web browser. VS Code is optional.
- On Windows, use **PowerShell** for the main instructions below. Git Bash commands are provided separately.

| Direct dependency | Pinned version |
| --- | --- |
| Streamlit | `1.66.0` |
| pytest | `9.1.1` |
| tzdata | `2026.2` |

Install from `requirements.txt`; pip also installs the required supporting packages. SQLite support comes with the standard Windows Python installation, so no separate database server is needed.

## First-Time Installation: Windows PowerShell

**Run one command at a time. Wait for the `PS ...>` prompt to return before entering the next command.** Copy the command only, without the terminal prompt.

### 1. Open the FoodTracker folder

Extract the project first. Find the folder containing both `run.py` and `requirements.txt`.

Open that folder in File Explorer, click its address bar, type `powershell`, and press Enter. Alternatively, right-click the FoodTracker folder in VS Code and select **Open in Integrated Terminal**, then select a PowerShell terminal.

To enter it from an existing terminal, use `cd` with your own path. For example:

```powershell
cd "D:\FIT1056 WORK\FIT1056-Group04-FoodTrack\FoodTracker"
```

Check that you are in the correct folder:

```powershell
Get-Item .\run.py, .\requirements.txt
```

Both files should be listed. If either is missing, correct the folder before continuing. Paths containing spaces must be enclosed in quotes.

### 2. Check Python

List the Python installations known to the Windows launcher:

```powershell
py -0p
```

Check the Python 3 version selected by the launcher:

```powershell
py -3 --version
```

It must be 3.11 or newer. If Python is missing, install it from the [official Python website](https://www.python.org/downloads/windows/), enable **Add python.exe to PATH** if offered, and reopen the terminal.

If `py` is unavailable but `python --version` identifies a suitable standard Windows Python, use `python` instead of `py -3` in the next step. Check `python -c "import sys; print(sys.executable)"` if you are unsure which installation it uses. An MSYS2 Python installation is a separate environment from the Windows Python used in this guide.

### 3. Create the virtual environment

A virtual environment is a local folder containing this project's Python interpreter and installed packages. It keeps the project's dependencies separate from other projects. Python itself must be installed first; `venv` is included with standard Python.

From inside FoodTracker, run:

```powershell
py -3 -m venv .venv
```

To choose a specific installed version, replace `-3` with its version, for example `py -3.14 -m venv .venv` or `py -3.12 -m venv .venv`. Only select a version listed on your computer.

Check the result:

```powershell
Test-Path .\.venv\Scripts\python.exe
```

The result must be **`True`**. If it is `False`, resolve the environment creation error before continuing.

**Create `.venv` on the computer where it will run.** If you receive a project containing someone else's `.venv`, or move the project to a different path, close programs using that environment, remove only the `.venv` folder, and recreate it here. Keep the source files and databases.

### 4. Install the dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Wait for installation to finish. `Successfully installed ...` means packages were installed; `Requirement already satisfied` means they are already present. If an `ERROR` appears, resolve it before proceeding.

Updating pip is optional. A notice that a newer pip version is available is not an installation failure. If an update is needed, run:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

During an update, `Successfully uninstalled pip-...` is an intermediate step. Wait for the final installation result and the prompt to return.

### 5. Verify the environment

```powershell
.\.venv\Scripts\python.exe -c "import sys, streamlit, pytest; print(sys.executable); print('Streamlit:', streamlit.__version__); print('pytest:', pytest.__version__)"
```

The interpreter path should end with `FoodTracker\.venv\Scripts\python.exe`. The package versions should be Streamlit `1.66.0` and pytest `9.1.1`.

### 6. Run the automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The supplied version has **306 test cases**. Expect `306 passed` if all cases pass; runtime varies by computer. Save the actual result and any failure details. A failed or interrupted run is not a passing result.

### 7. Start Demo mode

```powershell
.\.venv\Scripts\python.exe run.py --demo
```

Open [http://localhost:8501](http://localhost:8501) in your browser. Use the Demo accounts shown on the sign-in page. Keep the terminal open while using the application; press **Ctrl+C** in that terminal to stop the server.

The manual installation above does not require `setup.ps1`, virtual environment activation, or a PowerShell execution-policy change.

### Alternative: use the Windows installer

With the supplied `setup.ps1` in FoodTracker, you may use it instead of the manual environment-creation and package-installation steps:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

This starts a separate Windows PowerShell process with a process-only execution policy. It does not permanently change the computer's execution policy. Organizational Group Policy can still override a process setting; if it does, follow the manual installation instructions or contact the computer administrator.

The installer locates a standard Windows Python 3.11+ interpreter, creates `.venv` when absent, reuses a valid existing environment, installs `requirements.txt`, and checks package consistency and imports. It does not start the app, run pytest, create accounts, or modify application databases. `Ready.` appears only after installation checks succeed. Run the test and Demo commands shown at the end yourself.

If `.venv` is broken or copied from another computer, close programs using it and request recreation explicitly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -RecreateVenv
```

This removes only the old `.venv` before creating a new one. It first checks for a suitable base Python; if none is found, the existing environment is kept. A `.venv` link/junction is not removed automatically.

To choose a particular base interpreter, use its actual path. For an existing environment, include `-RecreateVenv` when changing the interpreter:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Python "C:\Path To Python\python.exe" -RecreateVenv
```

A script cannot resolve an execution-policy block from inside itself: Windows checks the policy before executing it. Use the `powershell.exe ... -File` command above when direct `.\setup.ps1` execution is blocked. No administrator elevation is required for a normal user-owned project folder.


## VS Code Interpreter

Installing packages in `.venv` does not automatically make every VS Code window use it.

1. Install Microsoft's **Python** extension if the interpreter command is unavailable.
2. Open the FoodTracker folder in VS Code.
3. Press **Ctrl+Shift+P** and select **Python: Select Interpreter**.
4. Select this project's `.venv\Scripts\python.exe` on Windows, or `.venv/bin/python` on macOS/Linux.
5. If it is absent from the list, choose **Enter interpreter path...**, then **Find...**, and locate the file manually.
6. Wait for analysis to finish. If an import warning remains, run **Developer: Reload Window** from the command palette.

For this project, select the local `.venv`, rather than a global interpreter such as `C:\msys64\mingw64\bin\python.exe`. If `streamlit` remains underlined, run the environment verification command above and read the actual VS Code warning.

## Optional Virtual Environment Activation

Activation lets you type `python` instead of the full `.venv` interpreter path. It is optional: all main Windows commands above work without it.

| Terminal | Activate from the FoodTracker folder |
| --- | --- |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| Windows Git Bash, using a Windows-created environment | `source .venv/Scripts/activate` |
| macOS/Linux Bash or Zsh | `source .venv/bin/activate` |

After activation, verify the interpreter with `python -c "import sys; print(sys.executable)"`. The prompt usually displays `(.venv)`. Use `deactivate` to leave the environment.

**Activation does not change your current folder.** You still need to enter FoodTracker before running `run.py`. Activation also applies only to the current terminal session.

If PowerShell blocks `Activate.ps1`, you can continue using `.\.venv\Scripts\python.exe` directly. For a trusted local script, an alternative is:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

If confirmation is requested, enter `Y`. This affects only the current PowerShell process and ends when it closes; it does not permanently change the computer's execution policy.

## macOS and Linux Installation

Open a terminal in FoodTracker. Confirm that `python3 --version` is 3.11 or newer, then run each command separately:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/python run.py --demo
```

Open [http://localhost:8501](http://localhost:8501). If environment creation reports a missing `venv` or `ensurepip` component, install the matching Python virtual-environment package using your operating system's package manager, then retry creation.

## Windows Git Bash

On Windows, an environment created with standard Windows Python uses **`Scripts`**, even when you open Git Bash. The `.venv/bin/python` path belongs to a macOS/Linux environment.

After completing installation, enter the project using your actual path and start it with:

```bash
cd "/d/FIT1056 WORK/FIT1056-Group04-FoodTrack/FoodTracker"
./.venv/Scripts/python.exe run.py --demo
```

Do not execute `setup.ps1` directly in Bash. To switch to PowerShell, enter `powershell.exe`, then use the PowerShell instructions.

## Starting the App After Installation

**Installation is normally needed only once per project location and computer.** For later use, enter FoodTracker and run:

```powershell
.\.venv\Scripts\python.exe run.py --demo
```

On macOS/Linux, use `.venv/bin/python run.py --demo`. Open the local browser address and keep the server terminal running.

| Action | When it is needed |
| --- | --- |
| Create `.venv` and install dependencies | First installation, a different computer/path, or a missing/damaged environment. |
| Install from `requirements.txt` again | Dependencies change or packages are missing. |
| Select the VS Code interpreter | First setup, a new project window, or an incorrect interpreter selection. |
| Activate `.venv` | Optional convenience in each new terminal. |
| Run pytest | When validating a release or after relevant code/dependency changes. |
| Start the server | Whenever it has stopped and you want to use the app again. |

The Windows `setup.ps1` reuses a valid `.venv`; only `-RecreateVenv` requests replacement. The macOS/Linux `setup.sh` still recreates `.venv`. Both scripts are installation helpers, not everyday startup commands.

## Demo and Normal Operation

| Mode | Start command on Windows | Default database | Accounts |
| --- | --- | --- | --- |
| Demo | `.\.venv\Scripts\python.exe run.py --demo` | `data/demo.sqlite3` | Synthetic accounts are created when the Demo database does not exist. |
| Normal | `.\.venv\Scripts\python.exe run.py` | `data/foodshare.sqlite3` | Create the first administrator explicitly; no automatic privileged accounts. |

Demo usernames are `admin`, `manager`, `staff`, `volunteer`, `recipient`, `recipient2`, and `recipient3`. Their initial password is **`DemoPassword123!`**. These are demonstration credentials only; use the sign-in page for the available Demo account guidance. Subsequent starts reuse the existing database and preserve changes.

For normal operation, stop the Demo server and open a terminal in FoodTracker. Ensure `FOODSHARE_DB` is unset unless you intentionally want a custom database, and `FOODSHARE_DEMO` is unset unless you intentionally want Demo mode. Create the first administrator:

```powershell
.\.venv\Scripts\python.exe manage.py create-admin
```

Enter the username, display name, and a password of 15 to 128 characters when prompted. Password entry is hidden. Then start:

```powershell
.\.venv\Scripts\python.exe run.py
```

An IT Admin manages Managers; a Manager manages Staff and Volunteers. Public self-registration creates Recipient accounts. Administrator-to-administrator management requires current-password confirmation, and the last active administrator cannot be deactivated.

`FOODSHARE_DEMO=1` also enables Demo mode. `FOODSHARE_DB` overrides the default database in either mode. For example, select an isolated test database in PowerShell with `$env:FOODSHARE_DB = "D:\FoodShareTests\test.sqlite3"`; remove the override with `Remove-Item Env:FOODSHARE_DB -ErrorAction SilentlyContinue` when finished. Do not use a classroom database for real operation.

Use **`run.py`** as the launcher. Directly running `app.py` as ordinary Python does not start the application correctly. Launching with `streamlit run app.py` omits this project's persistent login-cookie routes and provides tab-only authentication.

## Features and Business Rules

| Feature | Behavior |
| --- | --- |
| Accounts and access | Role, record ownership, account state, and assigned volunteer tasks control access. Deactivation revokes sessions. |
| Donations | Donors book without an account and receive a reference. Staff or an assigned Receiving Volunteer records accepted items and receipt history. |
| Inventory | Search and manage batches, quantities, expiry, safety status, stock corrections, and per-item low-stock thresholds. |
| Recipient needs | Store household needs, confirmed allergy information, dietary restrictions, and cultural/accessibility requirements with access controls. |
| Allocations | Staff manually select suitable food and reserve stock. The system checks current needs, safety information, expiry, and availability. |
| Collection | Record actual issued quantities once; deduct physical stock and release unused reservations in the same transaction. |
| Private swaps | Recipients request changes to their own uncollected items. Staff approve a suitable replacement and quantity, or decline with a response. |
| Pickup notices | A changed pickup schedule creates an unread notice for the affected Recipient. |
| Volunteer tasks | Assign, edit, or cancel dated tasks. Receiving and Distribution authority follows active tasks of the appropriate type. |
| Pickup queue | Authorized users check in arrivals and update service state. Recipients see their own approximate position/wait, without other recipients' details. |
| Anonymous feedback | Public submission, including while signed in; private review/archive by authorized Staff and Managers. |
| Reports and audit | Date-range reports, CSV export, stock history, and role-restricted append-only audit records. |

Important rules:

- **Food safety:** Unconfirmed allergy/allergen information and known allergy/diet conflicts block allocation and collection. Staff must inspect real labels; the application cannot infer undeclared allergens.
- **Stock:** Reserved stock remains on hand until issued. Available stock equals on-hand stock minus active reservations. Corrections retain a reason code, before/after values, actor, and source/reversal links where applicable.
- **Late collection:** After the booked window ends, Staff may permit same-day check-in/collection with an exception reason. This never overrides food safety, account restrictions, insufficient stock, or duplicate-collection protection.
- **Missed pickup:** From the following day, after the actual window has ended, an uncollected allocation expires and releases its reservation. A window crossing midnight remains valid until its end. Expired/cancelled allocations require a new allocation.
- **Recipient deactivation:** Uncompleted allocations are cancelled, reservations released, active swaps/queue entries closed, notices removed, and sessions revoked.
- **Queue estimate:** Order follows server check-in time and queue-entry ID. With `a` people ahead and an average service duration `m`, the waiting range is approximately `a*m` to `(a+1)*m` minutes; default `m` is 5. Serving, paused, and unarrived states have no waiting estimate. Queue fragments refresh every 20 seconds during normal operation and do not renew idle sessions.
- **Feedback:** Accept 1 to 500 trimmed Unicode characters. Persist only the message, submission date, review/archive flags, and record ID. Transient forms are single-use, with five successful submissions per anonymous browser token in ten minutes. No account/IP link is stored with feedback.
- **Public limits:** Shared caps per ten minutes are 60 donation bookings, 300 status lookups, 30 registrations, and 120 feedback submissions. These are site-wide prototype limits, not individual quotas.
- **Sessions:** Passwords use salted scrypt hashes. Five failed attempts within 15 minutes trigger a fixed 15-minute lockout. Sessions expire after 15 idle minutes or eight hours in total.

## Automated Tests

From FoodTracker, run:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

To run the suite and replace the local evidence files with a new report:

```powershell
.\.venv\Scripts\python.exe tools\verify_release.py
```

On macOS/Linux, use `.venv/bin/python -m pytest` or `.venv/bin/python tools/verify_release.py`. The evidence tool waits for the suite to finish before printing its captured test output.

| Evidence | Contents |
| --- | --- |
| [validation.json](docs/evidence/validation.json) | Environment, dependency versions, source hashes, command, exit code, and totals. |
| [pytest-output.txt](docs/evidence/pytest-output.txt) | Saved pytest output. |
| [pytest-results.xml](docs/evidence/pytest-results.xml) | Individual cases in JUnit XML format. |
| [server-smoke.json](docs/evidence/server-smoke.json) | Basic HTTP/server smoke-check results. |

The current prepared-release run started on **23 October 2026 at 00:17:36 MYT** and completed at approximately **00:19:20 MYT**: **306 passed, 0 failed, 0 errors, 0 skipped**, in **103.399 seconds**, using Python 3.12.14/Linux. Parametrized cases count separately. This is not a code-coverage percentage or proof of every SRS acceptance condition. The source hashes match the supplied application and test files. Pytest does not execute the Windows installer; that exact script received a separate PowerShell syntax check, while native Windows installation remains to be verified. The historical Windows run and initial failed Linux reproduction are preserved separately in `docs/evidence/automated/`.

## Manual Testing

Use Demo data or an isolated database copy. Record the tested version, tester, date, steps, expected result, actual result, pass/fail, and available screenshots or recordings. Keep completed manual results separate from the bundled automated run; the checklist below is a procedure, not a claim that these checks have passed on every computer.

| Test | Procedure and expected result |
| --- | --- |
| Installation and startup | Install in a new folder, run pytest, then start Demo. Dependencies install, all applicable tests pass, and the browser opens the app. Record Python/version output and terminal results. |
| Donation to inventory | Book a donation, retain its reference, and receive it as an authorized user. Only accepted quantities enter stock; confirmation and receipt history agree. |
| Needs and safe allocation | Confirm recipient allergies and food allergens, allocate suitable food, then try a known conflict. Suitable allocation succeeds; unsafe/unconfirmed allocation is rejected. |
| Partial collection | In an isolated scenario, create one food batch with 10 units and allocate 3. Check in the recipient and issue 2. Expect on-hand 8, reserved 0, available 8; a second collection of the same allocation is rejected. |
| Private swap and notices | Request a swap as Recipient, decide it as Staff, and verify replacement quantities/reservations. Change the pickup time and confirm that the owning Recipient sees the updated schedule and notice. |
| Sign-in lifecycle | Refresh while signed in; sign out and try refresh, a protected URL, and Back; leave a session idle for at least 15 minutes; deactivate another logged-in account using an authorized role. Valid login survives refresh; ended, expired, or revoked sessions cannot continue using protected data. |
| Two browsers and privacy | Use separate browsers for Staff and Recipient. Change pickup, swap, and collection state as Staff; check the Recipient's result. Confirm that another Recipient's records are inaccessible. |
| Queue refresh and disconnect | Leave the Recipient queue open while Staff changes the people ahead. Expect updates within 30 seconds. Simulate browser offline mode or stop the server; inspect unavailable/stale estimate guidance and the last confirmed time, then reconnect. Record any mismatch as a defect. |
| Keyboard and readability | Use Tab, Shift+Tab, and Enter; zoom the browser; inspect focus and text statuses, including grayscale. Essential controls remain usable and status is understandable without color alone. |
| Reports and CSV | Export a report for a known date range. Compare displayed totals and rows with the downloaded CSV and recorded transactions. |
| Persistence and recovery | Restart the server and confirm saved records remain. Back up a test database, change it, stop the app, restore, and compare counts and key records. Record recovery time. |
| Staff usability | Recruit five representative first-time Staff users; provide no more than one hour of training. At least four must independently complete donation receiving, inventory search, and needs viewing without facilitator correction. Record time, errors, assistance, and observations using the session template. |
| Performance | Prepare 1,000 business records, five concurrent users, and 100 specified operations. Measure responses: at least 95 must complete within two seconds. A subjective impression of speed is insufficient. |
| Deployment and peer review | On actual HTTPS, inspect HttpOnly, SameSite=Strict, and Secure cookie behavior, session lifecycle, and request/server-log privacy. Have a teammate review permissions, business rules, error guidance, and documentation; record findings and retests. |

Disconnecting Wi-Fi may not interrupt a localhost connection. Use browser offline simulation or stop the server for that check. A headless AppTest result does not establish real-browser disconnect or accessibility behavior.

## Data, Backup, and Recovery

SQLite saves records between restarts. The default files are `data/foodshare.sqlite3` for normal operation and `data/demo.sqlite3` for Demo, unless `FOODSHARE_DB` overrides them.

**Management commands do not inherit `--demo` from a separately running server.** By default they target the normal database. Explicitly select the intended database before a Demo backup, restore, or maintenance operation.

For example, in PowerShell, select the Demo database and make a backup:

```powershell
$env:FOODSHARE_DB = Join-Path $PWD.Path "data\demo.sqlite3"
.\.venv\Scripts\python.exe manage.py backup
```

The command prints the backup path. To restore it, stop all app instances writing to that database, keep the same database selection, and substitute the actual printed backup filename:

```powershell
.\.venv\Scripts\python.exe manage.py restore "backups\foodshare-YYYYMMDD-HHMMSS.sqlite3"
```

Restore validates the file, schema, integrity, and stored records before replacement, and makes a safety backup of an existing database. Check the restored data, then restart the server.

Remove the override when finished:

```powershell
Remove-Item Env:FOODSHARE_DB -ErrorAction SilentlyContinue
```

Without an override, the following commands target the normal database:

```powershell
.\.venv\Scripts\python.exe manage.py backup
.\.venv\Scripts\python.exe manage.py maintenance
.\.venv\Scripts\python.exe manage.py reset-admin
```

`reset-admin` resets an existing active IT Admin's password and revokes that account's sessions. Restrict this local operation to an authorized operator.

Maintenance checks overdue pickups on app activity and runs retention cleanup at most once per hour unless forced with `manage.py maintenance`. It removes feedback older than 90 calendar days and invalid sessions. With no app activity, cleanup waits for the next activity or an externally scheduled management command.

Before a v1-to-v2 migration, the application creates `<database>.pre-v2.sqlite3`; migration failure restores that backup. Version 2 removes earlier feedback rating/category fields while retaining messages, dates, and review flags. Legacy allergy/allergen information requires confirmation. Rehearse upgrades on a copy with writers stopped. A pre-v2 backup is for rollback with the previous application version, not the v2 restore command.

## Access From Other Computers

`localhost` means the computer opening the address. Sending someone `http://localhost:8501` does not connect them to your server.

| Option | Behavior |
| --- | --- |
| Each person installs locally | Each runs the project and opens their own localhost address. Their databases and changes are independent. |
| One server on a local network | Clients use the server's reachable IP/hostname and port. They share its database. HTTPS, network routing, and firewall access must be configured. |
| Hosted deployment | Clients use the deployed HTTPS address. Hosting, persistent storage, certificates, and network configuration must be provided separately. |

For the supported network launcher, provide a valid certificate and private key. Example for Demo in PowerShell:

```powershell
.\.venv\Scripts\python.exe run.py --demo --network --cert "C:\certs\certificate.pem" --key "C:\certs\private-key.pem"
```

Replace those paths with actual files. Open the HTTPS address printed by the launcher from another reachable computer. The certificate must be trusted and valid for the address being used. Network mode without HTTPS is rejected. For normal network operation, omit `--demo`.

The `run.py` routes set the persistent login cookie through a same-origin, CSRF-protected, single-use handoff. The cookie is HttpOnly and SameSite=Strict; HTTPS adds Secure. Verify the actual browser and deployment behavior during acceptance testing.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `requirements.txt` cannot be found | Enter the FoodTracker folder containing that file. In PowerShell, locate it with `Get-ChildItem -Recurse -Filter requirements.txt \| Select-Object FullName`, then `cd` to its parent folder. |
| `run.py` cannot be found | Check the current folder with `Get-Location` and list it with `dir`. Activating an environment does not enter the source folder. |
| `.venv\Scripts\python.exe` is not recognized | Check `Test-Path .\.venv\Scripts\python.exe`. Enter the correct folder and create the environment there if missing. |
| `No module named streamlit` or `pytest` | Install `requirements.txt` with this project's `.venv` Python, then use that same interpreter to run the app/tests. |
| Yellow underline under `streamlit` in VS Code | Select FoodTracker's `.venv` interpreter and verify the import. Read the warning if it persists. |
| `running scripts is disabled` | Use the explicit `.venv\Scripts\python.exe` commands; no activation script is required. For optional trusted PowerShell scripts, see the process-only setting above. |
| `py.exe: No suitable Python runtime found` | Run `py -0p` and select an installed Python 3.11+ version. Replace an older `setup.ps1` that stops during version probing, or follow the manual installation path above. |
| Bash reports `Set-Location: command not found` | A PowerShell script was executed in Bash. Switch to PowerShell or use the Windows Git Bash commands above. |
| Git Bash reports `.venv/bin/python: No such file or directory` | A Windows environment uses `.venv/Scripts/python.exe`. Also check that you are inside FoodTracker. |
| PowerShell treats `D:\FIT1056` as a command | Quote paths containing spaces. Use `cd "D:\folder with spaces\FoodTracker"` for navigation, or `& "D:\folder with spaces\FoodTracker\.venv\Scripts\python.exe" run.py --demo` to execute an interpreter. |
| Prompt shows `>>` unexpectedly | Press Ctrl+C, then enter one complete command with balanced quotes. Do not copy prompt characters. |
| `Operation cancelled by user` | The command was interrupted; it does not prove installation completed. Retry the relevant installation step and wait for its result. |
| Browser cannot connect | Keep the server running and inspect its terminal output. Confirm the printed address and port. |
| Port 8501 is already in use | Stop the other server or run `.\.venv\Scripts\python.exe run.py --demo --port 8502`, then open `http://localhost:8502`. |
| Wrong accounts or unexpected data appear | Check the project copy, running server/port, Demo flag, and `FOODSHARE_DB`/`FOODSHARE_DEMO` environment variables. Different copies can have independent databases. |

If a step fails, keep the full error text and resolve it before proceeding. Do not repeatedly reinstall a working environment merely to restart the app.

## Architecture and Verification Limits

Views render the interface; services check authorization and current state; domain functions express validation rules; storage handles SQLite transactions and migrations. Reserved quantities are derived from allocation records within a database snapshot.

- [Current implementation diagrams](docs/diagrams/CURRENT_IMPLEMENTATION.md): architecture, data relationships, and four sequences.
- [SQLite record schema](docs/diagrams/sqlite-record-schema.json).
- [Staff usability session template](docs/USABILITY_SESSION_TEMPLATE.md).

The automated evidence covers many functional, concurrency, rollback, migration, and UI cases. It does not certify every possible interleaving, real-browser behavior, all accessibility needs, the specified performance load, five-person usability acceptance, or the deployed HTTPS/logging configuration. Retain separate evidence for manual checks performed by the team.

Sensitive needs are stored as plaintext in SQLite. POSIX file permissions are restricted; disk encryption, Windows access controls, and backup protection remain deployment responsibilities. Anonymous token memory assumes one server process; multiple workers would require shared coordination.

When distributing source, exclude `.venv`, caches, real credentials, live databases, and private backups. Each user creates their own environment and installs from `requirements.txt`.

## Functional Requirement Reference

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

## Non-Functional Evidence Reference

This table distinguishes technical evidence from acceptance records that must be retained for the tested build and deployment. It does not assign pass/fail to the team's separate manual sessions.

| Requirement | Available technical evidence | Acceptance evidence to retain |
| --- | --- | --- |
| NFR-01: Access control | Service role/ownership/task denials, menu tests, and expired/inactive session rejection. | Deployment permission matrix and actual browser endpoint checks. |
| NFR-02: Usability | Runnable workflows and a Staff session template. | Five first-time Staff sessions, the training limit, and at least 4/5 completing all three tasks independently. |
| NFR-03: Atomic saves | Transaction rollback, injected receipt/history/notice failures, and no partial distribution assertions. | Relevant failure/recovery observations; tests do not establish every possible save failure. |
| NFR-04: Recovery | Current backup/restore, v1 preservation fixtures, pre-upgrade backup, and injected migration failure recovery. | Complete-dataset rehearsal and independently measured recovery against the 30-minute target. |
| NFR-05: Performance | Read-only session validation, indexed navigation counts, reduced dashboard scans, and date-filtered reports. | The 1,000-record, five-user, 100-operation timing baseline, with at least 95 operations within two seconds. |
| NFR-06: Maintainability | Feature modules, rule/transaction comments, public interfaces, source hashes, tests, and implementation diagrams. | Teammate code review and contribution sign-off. |
| NFR-07: Respectful interaction | Plain guidance, optional private swap reasons, minimal needs summaries, and escaped text. | Human review of wording, dignity, and participant understanding. |
| NFR-08: Accessibility | Text statuses for safety, pause, expiry, and denied actions. | Browser keyboard, visible-focus, zoom, grayscale, and relevant assistive-technology checks. |
| NFR-09: Authentication | Salted scrypt, password length checks, fixed lockout, idle/absolute expiry, and passive-refresh tests. | Browser refresh persistence, logout, timeout, deactivation, and recovery checks on the actual deployment. |
| NFR-10: Concurrent updates | Fifty rounds of three two-connection race scenarios, inventory invariants, and additional collection/replay tests. | System-level concurrent use and reconciliation observations; all possible interleavings are not claimed. |
| NFR-11: Feedback privacy | Minimal feedback fields, no stored submitter/account/IP link, no submission-linked audit, and disabled usage analytics. | Browser request and server/proxy-log inspection; users may still type identifying information voluntarily. |
| NFR-12: Queue updates | Private queue projection, 20-second fragments, simulated refresh-failure timestamp retention, and idle-refresh tests. | Measured browser update timing, offline/reconnect behavior, and behavior under the stated load. |
| NFR-13: Security and audit | Append-only audit, denied safety events, role separation, CSRF-protected cookie handoff, and HTTPS requirement for network launch. | Trusted-certificate browser/cookie checks, tampered request/WebSocket checks, and operational audit review. |


## Submission Evidence and Report

The completed English SRS is included as PDF and editable Word files in `docs/report/`, with `SRS_Findings.md` listing deviations and outstanding acceptance. Rendered implementation figures are in `docs/report/figures/`. The report follows the actual Streamlit/sqlite3 code and uses the recorded test evidence. Start with `docs/evidence/README.md` for the automated results, manual screenshots, original CSV, and distinctions between observed, tester-confirmed and unknown results. `docs/RELEASE_REVIEW.md` records package changes, source comparisons and remaining requirements gaps.

The supplied historical Windows run predates the current `setup.ps1`: its business-code hashes match, but its installer hash differs. The current Linux pytest run covers the supplied application and test files; it does not execute a native Windows installer. Reviewer identities, contribution sign-off, exact browser versions and participant outcomes must not be inferred from automated tests.

Manual check 7 (moderated usability sessions) and check 9 (team peer review) are Unknown / Not completed. Keyboard, zoom and wording checks confirmed by the tester are separate from the five-person usability target. Offline queue behavior is only partially demonstrated; a connection-error dialog is not evidence that a Recipient estimate was explicitly labelled unavailable. Recovery timing for the user's manual session was not recorded.

### Demo backup and restore in Windows Git Bash

Run inside FoodTracker in the same Git Bash terminal. Stop the server before changing or restoring its database. Use a Windows-native absolute path when exporting to Windows Python:

```bash
export FOODSHARE_DB="$(pwd -W)/data/demo.sqlite3"
./.venv/Scripts/python.exe -c "import os; from foodshare import data_path; p=data_path(); print(p); assert os.path.isfile(p), 'Demo database is missing'"
./.venv/Scripts/python.exe manage.py backup backups/demo-before-restore-test.sqlite3
./.venv/Scripts/python.exe run.py --demo
```

Record the initial values, change test stock or needs, stop with Ctrl+C, then restore:

```bash
./.venv/Scripts/python.exe manage.py restore backups/demo-before-restore-test.sqlite3
./.venv/Scripts/python.exe run.py --demo
```

Use a new backup filename for each rehearsal. Do not run `seed.py --reset` during a restore check. Closing the terminal clears this override; set it again before management commands in a new terminal. When returning to normal operation, stop the server and use `unset FOODSHARE_DB FOODSHARE_DEMO`.

### Git tracking of local environments

`.gitignore` excludes local environments recursively. Keep your own working `.venv` if useful; distribute source and `requirements.txt`, not installed packages. If Git already tracks it, run this from FoodTracker and review the staged changes:

```bash
git rm -r --cached --ignore-unmatch .venv venv env
git status --short
```

This untracks the folders without deleting their local files. A `.gitignore` rule does not remove items already committed or erase repository history. Commit and push the reviewed source/evidence changes through the team's normal process. This prepared ZIP contains no Git history and does not establish that a remote push has occurred.

Manual tester attribution is **DeanChan**. Check 9 is an independent group member review of code, UI and README; it is not a summary of previous tests, so its reviewer and outcome remain **Unknown / Not completed**. See SRS Section 12.5 for baseline deviations, including restricted Staff late check-in and separately committed lifecycle maintenance.
