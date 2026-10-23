# SRS findings and outstanding acceptance

Revision date: 23 October 2026 MYT. All authored deliverables are English.

The report preserves FR-01 to FR-57, AC-01 to AC-80, NFR-01 to NFR-13 and NAC-01 to NAC-13. Section 12.5 is the complete deviations register. Sections 9 to 12 and 14 use the executed/manual results.

Manual tester: DeanChan. Check 9 requires another actual team member to review code, UI and README; it is not a summary of previous tests. Its reviewer remains unassigned.

| ID | Area | Finding | Evidence or action | Status |
| --- | --- | --- | --- | --- |
| D-01 | Architecture and modelling | Earlier Flask/SQLAlchemy and conceptual Python entity-class descriptions do not describe this release. | Sections 6, 8 and 10 now describe Streamlit, service modules, dictionaries and sqlite3. Baseline design changed; functional targets retained. | Reconciled documentation |
| D-02 | FR-55 closed-window admission | Code permits a same-day late check-in by Staff with a reason, while the baseline says closed-window allocations shall not admit new check-ins. | queue.check_in and late-collection tests enforce a restricted exception; Volunteers/Recipients cannot use it. Decide explicitly whether to approve a requirement amendment or remove the exception. | Behavioral deviation open |
| D-03 | FR-14 reservation representation | Baseline refers to recorded/stored reserved quantities; code derives reservations from active allocation items. | Derived values enforce the quantity equation without duplicate counters; the report explicitly explains the representation. | Design clarification |
| D-04 | FR-43 / NFR-03 transaction wording | Lifecycle maintenance may commit expired allocations/swaps before a later decision transaction fails; the baseline groups affected closures with the triggering transaction. | refresh_swap_lifecycle and expire_overdue_allocations are separate maintenance transactions. Diagrams show this explicitly. Clarify the requirement or refactor; a failed decision does not undo prior legitimate expiry work. | Boundary deviation open |
| G-01 | NFR-02 / NAC-02 | Five first-time Staff study and 4/5 success result absent. | Manual check 7; no participant/training/timing data. | Unknown / Not completed |
| G-02 | NFR-06 / NAC-06 | Another team member's code/UI/README review absent. | Manual check 9; DeanChan is the completed manual tester, not a substituted independent reviewer. | Unknown / Not completed |
| G-03 | FR-54 / NFR-12 / NAC-12 | Complete Recipient disconnected estimate/unavailable/timestamp behavior not demonstrated. | Simulated service-error fallback passes; actual connection screenshots cover only part of requirement. | Partial |
| G-04 | NFR-05 / NAC-05 | Five-user, 1,000-record, 100-operation latency target not measured. | Concurrency invariants and suite duration do not measure this baseline. | Not demonstrated |
| G-05 | NFR-04 / NAC-04 | 30-minute service resumption after a real failed release migration not measured. | Manual restore passed functionally; copied-dataset restore matched every table/settings; real old-database failure rehearsal absent. | Partial |
| G-06 | NFR-11 / NAC-11 | Browser/server/proxy-log inspection for deployed anonymity incomplete. | Minimal schema, no submitter path and replay tests pass; voluntarily typed identifiers remain possible. | Partial |
| G-07 | NFR-13 / NAC-13 | Actual network certificate/cookie, tampered WebSocket/request and all-event deployment review incomplete. | HTTP CSRF/session and audit tests pass; no end-to-end security certification claimed. | Partial |
| G-08 | NAC-07 / NAC-08 | Two-reviewer wording check and full grayscale/assistive checks not completed. | One tester confirmed keyboard/zoom/text states; retain this narrower result. | Partial |
| G-09 | Installation acceptance | Exact current setup.ps1 not installed in a clean native Windows environment here. | Latest uploaded script matches; PowerShell parser passes. Execute Windows instructions before installer sign-off. | Not demonstrated |
| G-10 | Traceability and authorship | Final Git commit, per-member sequence authorship and human review date not verified. | Use source hashes and unassigned contribution fields; do not invent attribution. | Unknown |
| O-01 | Pickup selector observation | Saved pickup detail/notice agree but earlier selector shows former time. | OBS-01; reproduce current widget/options lifecycle. | Unclassified |
| O-02 | Queue-card observation | Allocated Recipient later lacks queue card in one image. | OBS-02; inspect actual time/state and current database before classifying. | Unclassified |

306 current automated cases passed, with no failures/errors/skips. This does not satisfy unmeasured performance, participant-study or deployment conditions. Manual checks retain their actual Pass/Partial status and evidence qualifications. No reviewer, participant, time measurement or Git commit is invented.
