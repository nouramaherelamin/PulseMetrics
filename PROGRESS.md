# PulseMetrics V2 - accepted project closeout

## Acceptance and scope
The project lead reports **15/15 manual acceptance checklist items completed successfully** and explicitly approves the current UI/UX. Reported coverage includes live monitoring; discovery/track/untrack; analytics; termination/history preservation; Time Machine/comparisons; alert activation/recovery/disabling; settings persistence; health; offline operation/startup; Exit/restart/history persistence.

These are **user-reported manual results**, not newly executed automated tests or independent graphical observations. No detailed fifteen-item execution log, browser/resolution information or screenshots were supplied; none are invented. See docs/testing.md for the acceptance record and retained reference checklist.

## Preserved implementation and automated evidence
Approved delivery candidate: `22ab0b6faf0c35b6f7d01fddd9709bb77f37646b`; existing tag `v2-delivery-candidate` remains at that commit. The closeout changes documentation only. Application source, UI/UX, layouts/colors/charts/navigation/styling, dependencies, tests and build/launch scripts remain identical to the approved candidate.

Prior automated evidence remains unchanged: fresh Release build passed; final V2 CTest 2/2 and pytest 14/14 passed (50.33s pytest); 44 installed runtime dependency pins/constraints matched. A prior actual application run committed 1,139 accepted observations and stopped cleanly. These tests were not rerun for documentation-only changes. Detailed source/binary evidence remains in docs/evidence/verification.json and the sibling build evidence directory.

## Retained exceptions and open review
- **Preservation exception:** three received legacy runtime files differ from the original baseline: `PulseMetrics/dist/database/pulsemetrics.db`, `PulseMetrics/dist/logs/collector.log`, `PulseMetrics/dist/logs/monitor.log`. Recorded write times: 2026-11-16T12:25:43Z; legacy activity is visible in those logs, but actor unverified. The last check matched 1,076/1,079 received files, specification 1/1, approved designs 5/5, initial audit 974/974 and protected audit 82/82, with no added received files. Full-tree preservation remains Failed, not waived by product acceptance. No originals restored/overwritten or baseline reset. See docs/evidence/preservation.json.
- **SQLite compiler warning:** retained SQLite 3.45.3 produces GCC 16.2 Release `-Wstringop-overread` in sqlite3Strlen30 inlined into sqlite3ColumnSetColl. Runtime tests passed; harmlessness is unproven. No patch, suppression or dependency change was made.
- **R-01: intermittent alert-to-supporting-window display observation.** User-reported and unresolved; not independently reproduced. Exact symptom/reproduction details, event/window IDs and cause were not supplied. No implementation change was made. Further investigation or fixes require separate authorization.

## Documentation checkpoint and delivery
This closeout records the lead's acceptance in PROGRESS.md, README and relevant testing/course/architecture documentation. Existing candidate commit/tag and automated/preservation evidence are preserved. The documentation-only commit and updated source archive are verified against Git; the archive SHA256 sidecar and package verification manifest are kept in `../PulseMetrics_V2_RELEASES/`.

Final checks: only Markdown documentation may differ from 22ab0b6; the working tree must be clean before packaging; all archive files must match committed Git blobs; generated binaries, caches, personal databases/logs and audit artifacts are excluded. No remote publication, Computer Use, browser automation, source changes, redesign, refactoring or new dependencies are authorized or performed.

## PC-monitoring UI redesign (post-closeout, presentation only)
A redesign of the Streamlit presentation layer was implemented on request (see docs/ui-redesign.md). Changed: `.streamlit/config.toml`, the theme flags in `python/pulsemetrics/controller.py`, `python/pulsemetrics/ui/{app,components,pages}.py`, new `ui/theme.py`, new `tests/ui_fixture.py` and `tests/test_ui_redesign.py`, plus documentation. Native code, schema, IPC, data access and analytics are untouched. Windows runtime, AppTest and the manual acceptance checklist have **not** been run for the redesign; the earlier 15/15 acceptance and UI approval apply to the previous UI, and the preservation exception, SQLite warning and R-01 remain as recorded.

## Remaining governance
Product/manual UI acceptance is recorded as approved. The existing preservation exception, SQLite warning and R-01 remain documented review items. University catalog/deadline, honest roster/contribution evidence and first-party licensing/publication policy remain separate lead responsibilities; no additional approvals for them are inferred. No implementation work should restart without a new instruction.

## Separate publication preparation
The sections above record original development closeout. This separate copy preserves sanitized history and adds publication documentation and preventive ignore rules only. See docs/publication.md for revision correspondence, approved email visibility and remaining permissions. Evidence remains historical; no application tests were rerun. No application/UI changes or remote publication occurred.
