# Code release review

Prepared on 23 October 2026 (MYT). This final project package includes the completed English SRS in PDF and editable Word format.

## Package decisions

- `setup.ps1` matches the latest supplied `FoodTracker(3).zip` byte for byte. It supports Windows Python discovery, explicit interpreter selection, reuse of a valid local environment, and explicit recreation of an unusable environment. PowerShell parser check passed on Linux. Native Windows installation of this exact script was not executed here.
- `README.md` merges the later English installation reference with the package's current architecture, Demo/normal database distinction, venv guidance and evidence limits. It includes Windows PowerShell and Git Bash commands separately.
- `.gitignore` excludes `.venv`, `venv`, `env`, `ENV`, caches, runtime databases, backups, local secrets and TLS keys, including nested environments.
- Local environments, generated runtime databases, backups, caches and bundled archives are excluded from the release ZIP. Existing source uploads remain untouched. Demo mode can recreate synthetic sample data.
- Evidence is retained under `docs/evidence/`, including the supplied screenshots and original CSV. These are assignment test records; review their displayed test names before making a repository public.
- Current diagrams and logical record schema are in `docs/diagrams/`; rendered figure assets are in `docs/report/figures/`. The revised SRS and SRS_Findings.md are included under docs/report/.

## Changes relative to the latest uploaded code ZIP

Application business logic, `run.py`, `manage.py`, `seed.py`, dependency pins and `setup.ps1` are unchanged. Five test files changed: `test_app.py`, `test_concurrency.py`, `test_new_features.py`, `test_review_fixes.py`, and `test_services.py`. Date-dependent test data now uses the application's site date/time instead of the execution host date/time. Assertions and business rules were not relaxed. The initial failing run remains in `docs/evidence/automated/linux-initial/`.

The prepared run has 306 passing pytest cases, 0 failed/errors/skipped, with exact application/test hashes in `docs/evidence/validation.json`. All those hashes were checked again before packaging. Documentation-only edits after that run do not change the tested application/test files.

`.gitignore` does not untrack files that are already committed. For an existing repository that already tracks a virtual environment, review `git ls-files .venv venv env ENV` and remove only those environment paths from Git's index with `git rm -r --cached --ignore-unmatch .venv venv env ENV`, then commit the ignore rule and index changes. The local environments remain on disk. Fresh uploads of this release contain no environment files.

## Remaining acceptance and evidence gaps

| ID | Finding | Current status |
| --- | --- | --- |
| GAP-01 | Planned Flask/SQLAlchemy architecture differs from implemented Streamlit and Python sqlite3, including generic record tables and JSON columns. | Reconciled in the v1.7 report; original design change stated explicitly. |
| GAP-02 | Original five-person usability target. | Trial completed: 3 participants, 30 minutes training, all tasks successful and no issues reported; five-person/no-correction acceptance remains partial. |
| GAP-03 | Full release-review checklist metadata. | Groupmate code review completed with no issues reported. Reviewer name/date/files and separate UI/README checklist not supplied; contribution sign-off remains separate. |
| GAP-04 | Complete Recipient queue offline fallback, explicit unavailable estimate and last-confirmed timestamp. | Partial evidence; screenshots do not demonstrate the full requirement. |
| GAP-05 | Five-user, 1,000-record, 100-operation measured performance target. | Not demonstrated. Concurrency tests are not performance acceptance. |
| GAP-06 | Manual end-to-end restoration against the 30-minute service-recovery target. | Functional recovery passed; browser recovery duration unmeasured. |
| GAP-07 | Real old-version database upgrade and real upgrade-failure recovery rehearsal. | Not performed; automated fixtures have narrower coverage. |
| GAP-08 | Actual network HTTPS/certificate, cookie, tampered request/WebSocket and proxy-log checks. | Deployment acceptance not demonstrated. Local service tests have narrower scope. |
| GAP-09 | Native Windows installation of current setup.ps1. | Syntax inspected; execute fresh-folder installation on Windows before claiming full installer verification. |
| OBS-01 | Earlier pickup selector showed an old time while details/notices showed the revised time. | Observation retained; no fix or retest invented. |
| OBS-02 | Allocated Recipient screenshot later lacked a queue card. | Context insufficient to classify; retain for investigation. |

These are honest verification limits, not claims that all listed behavior is broken. See `docs/evidence/README.md` for the manual evidence scope and report-section mapping. No participant identity, human reviewer, elapsed time or Git commit was invented. The source build SHA-256 is used where no trustworthy final Git commit is available.

The final report additionally records D-02 (restricted Staff late-arrival check-in differs from the baseline closed-window rule), D-03 (derived rather than separately stored reservations), and D-04 (lifecycle maintenance may commit before a failed decision transaction). See report Section 12.5 for the full acceptance distinction. DeanChan is attributed only as the completed manual tester; check 9 now has a completed groupmate code review with no issues reported; the reviewer name and exact scope checklist were not supplied.

Report v1.7 adds the owner-confirmed trial/review results received on 23 October 2026. The application and test source are unchanged, so the existing 306-pass run remains the recorded automated result; no new pytest execution is claimed for this documentation-only update.
