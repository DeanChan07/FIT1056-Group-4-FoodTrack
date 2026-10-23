# Evidence register

This register describes the evidence actually retained for the prepared code release. A passing test does not automatically satisfy every acceptance condition in the SRS. The completed v1.7 report and its requirement-by-requirement assessment are in docs/report/. Manual tester: DeanChan; peer code reviewer: groupmate, name not supplied; code review completed with no issues reported.

## Automated verification

| Evidence | Actual result | Scope and limit |
| --- | --- | --- |
| `validation.json`, `pytest-output.txt`, `pytest-results.xml` | 306 passed; 0 failures, errors or skips; Python 3.12.14, Linux; 103.399 seconds | Run started 23 October 2026 at 00:17:36 MYT. Source hashes identify the supplied application and tests. Pytest does not execute the Windows installer. |
| `automated/windows-submitted/` | 306 passed; submitted Windows/Python 3.14.2 record | Historical evidence. Application business-code hashes match the prepared release. The installer and five test files differ from this record. |
| `automated/linux-initial/` | 299 passed, 7 failed | Preserved initial reproduction. Tests mixed host-local dates with the application's Asia/Kuala_Lumpur date. Test fixtures were corrected to use the site date; business rules and expected results were retained. |
| `server-smoke.json` | Health, root and CSRF endpoints returned 200; missing-CSRF session request returned 403; normal database contained no default users | HTTP smoke check, not a browser, load or usability test. |
| `recovery/recovery-result.json` | Pass; all application tables and settings matched the baseline after restore; Staff service login succeeded | Independent rehearsal on a temporary copy of the uploaded complete Demo dataset. Original uploaded database was not modified. |

`recovery/rehearse_recovery.py` records how the independent rehearsal was performed. Its approximately 0.015-second restore-and-comparison duration is a small offline copy measurement, not an end-to-end browser recovery time or evidence for the 30-minute operational target.

## Manual verification

Screenshots are in `manual/`. Use `manual/screenshot-index.csv` or `.json` for filenames, descriptions, original names and SHA-256 values. The original exported report CSV is retained alongside them. Original screenshots are unchanged, including any browser or operating-system language. All authored documentation is English.

| ID | Check | Recorded outcome | Evidence and qualification |
| --- | --- | --- | --- |
| FLOW-01 | Book and receive a donation | Pass within observed workflow | E-211519 through E-211927: Grapes booking and receipt; accepted quantity 111 appears in stock. |
| FLOW-02 | Save needs and require Staff consent | Pass within observed workflow | E-212310 through E-212450: household size 2, peanut allergy, halal needs; Staff edit without consent denied. |
| FLOW-03 | Allocate and reserve stock | Pass within observed workflow | E-213535 and E-213603: allocation No.4; Rice 10 on shelf, 2 set aside, 8 available. |
| FLOW-04 | Approve private swap | Pass within observed workflow | E-213746 through E-213901: Pending to Approved, Halal chicken replacement and reservation changes; Recipient notice. |
| FLOW-05 | Change pickup and notify Recipient | Pass within observed workflow | E-213937, E-213951 and E-214000. An earlier selector label retained its former time while the detail and notice showed the changed time; retain as an observation rather than inventing a defect fix. |
| FLOW-06 | Check in and collect | Pass within observed workflow | E-214050 through E-214226, E-220100 and E-220315: No.4 Collected on both sides; chicken quantity 6 to 4. |
| FLOW-07 | Report and CSV | Pass within observed workflow | E-214328 and E-214428 plus original CSV. Automated tests provide additional report total checks. |
| MULTI-01 | Staff/Recipient synchronization in separate browsers | Pass, tester-confirmed | Tester used Chrome for Staff and Edge for Recipient. Screenshots support matching workflow records. Exact browser versions and per-step timing were not recorded. |
| MULTI-02 | Own-record display | Pass within normal page navigation | E-220749 through E-220808 and collection screenshots. Direct tampered access to another Recipient's record was not manually demonstrated. |
| SESSION-01 | Refresh preserves valid login | Pass | Tester confirmed refresh; E-220902 and E-220909 show matching needs and notices. |
| SESSION-02 | Logout blocks protected data | Pass | Tester confirmed refresh, copied URL and Back actions; E-221056, E-221104 and E-221109. |
| SESSION-03 | Idle timeout blocks next action | Pass, tester-confirmed with limited timing evidence | E-223208 shows session ended. Tester confirmed at least 15 minutes idle; precise start/end times were not retained. A connection-error screenshot is not timeout evidence. |
| SESSION-04 | Deactivation revokes session and prevents login | Pass, screenshots plus tester confirmation | E-223927, E-223935 and E-223955. Old page content remains visible in one image; blocked access/save after refresh was confirmed by the tester without a further screenshot. |
| QUEUE-01 | Queue automatically updates within 30 seconds | Pass, tester-confirmed | E-225227 and E-225334; exact elapsed seconds not recorded. E-225645's missing queue card is an unresolved observation, not proof of correct update. |
| QUEUE-02 | Disconnection, unavailable estimate and retained last-confirmed time | Partial / recipient fallback unverified | Connection-error dialog and Staff last-update time have screenshots (E-225742, E-225806, E-230144). Explicit Recipient estimate-unavailable wording and retained Recipient confirmation time were not demonstrated. |
| UI-01 | Keyboard and visible focus | Pass, tester-confirmed | Tester confirmed keyboard operation. No dedicated keyboard recording; connection-error images do not prove keyboard accessibility. |
| UI-02 | 150% and 200% zoom | Pass, tester-confirmed | Tester reported checks matched expectations; no dedicated zoom evidence retained. |
| UI-03 | Text communicates states and guidance | Pass within tester's checked scope | Screenshots contain Pending, Approved, Waiting and Collected text; comprehension is tester-confirmed. This earlier text-state check is separate from the three-person trial reported in the follow-up. |
| RECOVERY-01 | Demo backup, modify and restore | Pass, screenshots plus tester confirmation | E-232017 through E-234600: chicken 4 to 7 to 4; urgency Standard to Soon to Standard. Other baseline records were confirmed by the tester. Manual recovery duration not recorded. |
| CHECK-07 | Three-participant usability trial | Pass within reported trial; original NFR-02 partial | Owner confirms 3 participants, 30 minutes training, 3/3 successful task sets and no issues. Original five-person/no-correction criterion not fully verified. |
| CHECK-09 | Groupmate code review | Pass within reported code-review scope | Owner confirms groupmate reviewed code and found no issues. Reviewer name, date, exact files and separate UI/README checklist not supplied. |

The original screenshot-supported workflows were performed on 22 October 2026 MYT. The usability and groupmate-review confirmations were received on 23 October 2026 MYT; actual session/review dates were not supplied. Screenshot filenames are not precise elapsed-time measurements.

## Recovery artifact limitation

The uploaded runtime Demo database contained eight users and the test records, but the only backup found in the supplied ZIP was for the empty normal database. It is not represented as the user's Demo recovery backup. The screenshot-based recovery result and the independent copied-dataset rehearsal are separate evidence sources. Runtime databases and backups are excluded from this distributable code ZIP; fresh synthetic Demo data is created by `python run.py --demo`.

## Use in the report

| Report section | Evidence used |
| --- | --- |
| Sections 6, 8 and 9, implemented design and usability evaluation | Actual classes/records, current screens and tester keyboard/zoom/wording observations; completed trial: 3 participants, 30 minutes training, all tasks successful, no issues; original five-person target remains partial. |
| Section 10, sequence diagrams | Actual view-to-service-to-domain/storage calls; method names and transactional outcomes match code. |
| Section 11, quality assurance | Automated reports, manual test register, concurrency and recovery evidence, defect observations and unresolved acceptance conditions. |
| Section 12, implementation | Feature-to-code/test/evidence mapping, actual Streamlit/sqlite3 architecture and build hashes. |

The completed SRS follows the supplied template headings and records detailed deviations in Section 12.5. Individual reflection/contribution content is outside this revision's requested scope.

## Additional transaction boundary deviation

The report records D-04: lifecycle maintenance can persist timed allocation/swap closures before a later decision transaction fails. These are separate maintenance transactions, as shown in the actual sequences. The baseline wording about closures in the triggering transaction requires an explicit clarification or implementation change; no universal unchanged-domain-state claim is made across that maintenance boundary.

## Follow-up confirmations

See user-followup-results.json and .md for the owner-confirmed three-person usability trial and completed groupmate code review. These results replace the earlier uncompleted status; they do not invent individual timings, participant identities or reviewer sign-off.
