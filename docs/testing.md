# Verification and remaining acceptance

## UI redesign verification (PC-monitoring theme)

A presentation-only redesign (docs/ui-redesign.md) followed the accepted closeout. Verified where it was developed (a Linux sandbox **without Streamlit/Plotly and without Windows**): `compileall` of all Python; `tests/test_analytics.py` and `tests/test_data_config.py` (4 passed, `ctypes.WinDLL` stubbed for import only); the portable native `test_contract.c` assertions compiled with Linux gcc; and a 45-check logic harness that runs the real page/component code against stub `streamlit`/`plotly`/`ipc` modules and a real SQLite database built from `database/schema.sql` (healthy, stale, write-failure, missing-database and stopped states; gap breaks; exact widget labels and counts). **Not executed there:** Streamlit AppTest, the new `tests/test_ui_redesign.py`, all Windows-only tests (`test_collector.py`, `test_controller.py`, `test_monitor.py`, `test_ipc.py`), native Windows build/CTest, and any real browser rendering. Run `python scripts/verify.py --configuration Release` on Windows and repeat the manual checklist below before accepting the redesign. The 15/15 manual acceptance recorded further down applies to the previous UI.

## Automated evidence

Run from the repository:

```powershell
python scripts/verify.py --configuration Release
```

This configures/builds current native source, runs CTest and all pytest cases against those exact binaries, and records commands, return codes, timings, versions, Git revision, source hashes and executable hashes in a unique sibling `PulseMetrics_V2_BUILD/evidence/verification-*` directory. Tests create their databases outside source. `docs/evidence/verification.json` is the sanitized delivery manifest; detailed local logs remain beside the build.

Verified on Windows11 x64 build26200 / Python3.14.6 / UCRT64 GCC16.2.0:

| Check | Observed status |
|---|---|
| Fresh Release CMake/Ninja configure/compile/link | Passed; one retained SQLite vendor warning below |
| Current V2 CTest | 2/2 passed: protocol/math/capacity; SQLite/JSON/recovery/retention |
| Current pytest | 14/14 passed in the complete Release run |
| Original Phase0 baseline | Historical 5/5 passed; temporary legacy-only targets retired after V2 replacement. Earlier 7/7 = those five plus two V2 suites; it is not the current test count. |
| Measured sender -> native collector -> SQLite -> Analytics | Passed with actual sender process and stored observations |
| Overview and Explorer controls | Passed through Streamlit AppTest using real native monitoring and track/untrack |
| Analytics / Time Machine / Alerts | Passed through AppTest with real sender/history, threshold breach/recovery and previous-window interaction |
| Native shutdown/restart and retained history | Passed; failed-drain case reports uncommitted observations and non-clean result |
| Full graphical desktop/browser acceptance | Passed - project-lead reported manual acceptance; current UI/UX explicitly approved. Not independently repeated; no screenshots supplied/captured in closeout. |
| Offline operation and offline startup | Passed - project-lead reported manual checks; not an automated or independently repeated result. |

The two native suites cover exact grammar/bounds, independent counter/gauge/timer math, source/type separation, complete1,024-series capacity, partial-duration rate, write refusal/retry/idempotency, interrupted interval after final window, cross-session clock rollback, Unicode/duplicate JSON, retention and preserved open-alert evidence, repeated ended-state and post-end alert behavior.

Python tests cover real UDP arithmetic and malformed types, two actual source keys, oversized datagrams/framing/NUL/fragmentation, six pending batches including in-flight work, frozen active store and exactly-once recovery, failed shutdown, EOF flush, actual native process identity/access/track/untrack/end, named-pipe framing/instance protection, Job reaping, startup readiness with no browser, port conflict, settings idempotency/validation/atomic failure, read-only SQLite/missing schema errors, weighted summaries and cross-session comparison refusal. AppTest exercises backend-connected UI behavior; it does not test pixel layout or real browser chart gestures.

The first Job-reaping test expected a nonzero process exit code and failed. Windows returned0 despite prompt Job termination. The corrected test checks a live child, prompt termination and absence of its normal completion marker. The production controller requires an explicit native clean event plus exit status; it never equates exit0 with a clean native shutdown.

## Build warning

GCC16.2 Release optimization warns in retained SQLite3.45.3 `sqlite3Strlen30`, inlined into `sqlite3ColumnSetColl` (`native/vendor/sqlite3.c`, around34712/121484), about `-Wstringop-overread`. The helper has a null check; the warning concerns optimized caller pointer arithmetic. Required runtime tests pass, but that does not prove the warning is harmless. No warning suppression or speculative vendor patch was applied. Review/update the retained dependency with its own compatibility tests before broader distribution. No vulnerability advisory search or dependency upgrade is claimed.

## Historical automated graphical limitation

The browser connector returned `The browser access host is unavailable`. Desktop enumeration exposed a minimized Edge window; capture requested activation that the wrapper did not expose. The documented computer-use native helper then returned `failed to connect native pipe ... The system cannot find the file specified (os error 2)`. Further identical retries were stopped. This is an automation limitation, not evidence that the product GUI cannot render. A real local server ran and stopped cleanly with1,139 accepted native observations and zero uncommitted samples. No screenshot has been fabricated or copied from V1.

## Manual desktop procedure (acceptance reported complete)

The project lead reports completion of all 15 manual checklist items and approves the current UI/UX. The grouped reference procedure below is retained for future authorized verification; it is not a new request to repeat the review. No item-by-item execution log, browser/resolution details or screenshots were supplied with the closeout report, so none are invented here. The earlier automation limitation does not negate the user-reported acceptance.

1. At1366x768 and1920x1080, then125% Windows display scale, launch with one command. Confirm browser opens without needing a pre-existing client. Inspect all four navigation items, readable text/focus, balanced cards/charts, no clipped controls, navy surfaces and consistent purple/cyan accents. Capture each page.
2. Overview: wait two samples and a committed window. Confirm live CPU/RAM/sample timestamp changes; chart UTC window ends match stored observations and last commit is separately labelled. Use chart hover/zoom. Empty top-process state must explain tracking.
3. Explorer: search/sort/page, choose an accessible process, Track and Untrack. Confirm changing selection updates native history. Inspect PID/creation, warmup/unavailable fields and saved selections. Close a disposable process and confirm Ended/history preservation. Do not terminate unrelated programs.
4. Run `pulse_sender.exe --port 8125`. Analytics: select its source and confirm five operations, observed in-flight values and measured timer observations. Test ranges, chart selection -> Time Machine, and absence of CPU/response-time claims for uninstrumented programs.
5. Alerts: create a counter sum rule with a threshold below a real sender window's sum; run the sender again. Inspect the event's actual value/threshold/time; open its supporting window. Disable the rule and confirm the explicit closure reason. Backend automated fixtures separately prove recovery on a nonbreaching observation.
6. Time Machine: choose a saved UTC window, compare rows with SQLite `metric_windows`, use previous/next and a chart point. Stop/restart collection to create a real gap; confirm it is not interpolated or filled. Select empty/out-of-retention dates and inspect explanatory empty state. Confirm no cross-session comparison is invented.
7. Settings: change refresh, save and observe new cadence; change sampling/window and verify pending-restart notice, then Exit/relaunch to apply. Invalid window<sample must be refused. Collector Health must distinguish receiver status from write health/freshness.
8. Open two browser tabs. Close one: collection must continue. Exit explicitly in the other: wait for clean/failed status, verify owned processes stop and `last_shutdown.json` is truthful. Relaunch same data directory and inspect history. Avoid relying only on process exit code.
9. After dependencies are installed, perform the same navigation/sender/history workflow while the machine has no external connectivity (project lead may disconnect it manually). Loopback, local assets and history must still work. No system setting was changed by this implementation run.
10. Record failures and actual screenshots before signing the visual/offline gates. Do not label this checklist Passed merely because it exists.

Advanced stress benchmarks and original proposed quantitative load target T-15 are excluded by the approved scope. No performance-capacity claim is made beyond the deterministic bounded-resource tests.

## Retired baseline coverage cross-check

| Historical native test | Current replacement |
|---|---|
| parser: counter/gauge/timer, fractional conversion, batch, invalid input | test_contract.c exact-value/grammar assertions; real multiline UDP and bounded framing in test_collector.py |
| metrics: counter sum/count, gauge window reset, timer sum/min/max/count | test_contract.c independent fixtures including a new sample after an empty snapshot; test_collector.py persisted arithmetic |
| aggregator: rate/mean, empty windows, gauge last and timer rate | test_contract.c actual-duration counter and timer rates, no fake empty rows; test_analytics.py weighted mean; real persisted SQLite views |
| C presentation DAL: missing DB and read pipeline | test_data_config.py read-only/missing-schema errors; test_controller.py real collector -> SQLite -> UI |
| collector integration: UDP/threads/database | test_collector.py five actual native-process tests, plus monitor/controller lifecycle integration |

Retiring the old targets does not treat their old APIs as production coverage. Their meaningful behavioral assertions are retained in the new contracts; old internal gauge carry-forward storage is intentionally replaced by the approved absence-of-observation semantics. No tests were disabled to obtain a pass.

## Preservation exception

The final preservation assertion correctly failed on three received **legacy runtime** files: `PulseMetrics/dist/database/pulsemetrics.db`, `PulseMetrics/dist/logs/collector.log`, and `PulseMetrics/dist/logs/monitor.log`. Their modification timestamps are2026-11-16T12:25:43Z and the logs show legacy collector/monitor activity ending at14:25:43 local time. The actor cannot be established from these artifacts. No baseline reset, restoration or overwrite was attempted.

The other1,076 received files, original specification, five approved design files,974 initial-audit files and82 protected audit artifacts match their baselines. Complete received-tree preservation therefore remains **Failed / project-lead review required**, even though protected source/design/audit checks pass. The detailed hashes are in `docs/evidence/preservation.json`. This is the unresolved final AssertionError; the earlier Job exit-code test assumption was separately corrected and passed the full Release suite.


## Final project-lead acceptance record

Recorded UTC: 2026-11-17T19:52:00.501688+00:00. Evidence source: the project lead's explicit final-acceptance message, not a new agent test run.

**15/15 manual acceptance items reported successful; current UI/UX explicitly approved.** The supplied results cover live system monitoring; process discovery, tracking and untracking; historical analytics; process termination detection and retained history; Time Machine and historical comparisons; alert activation, automatic recovery and rule disabling; settings persistence; collector health; offline operation and offline startup; application Exit, restart and historical persistence. The exact fifteen individual checklist entries were not supplied; this record preserves the reported total and supplied coverage without inventing additional executions.

Approved implementation baseline: `22ab0b6faf0c35b6f7d01fddd9709bb77f37646b`, retained at tag `v2-delivery-candidate`. The closeout is documentation-only: no application source, UI, styles, charts, navigation, dependencies or tests changed; no Computer Use/browser automation or remote publication occurred. Prior Release build, 2/2 CTest and 14/14 pytest results remain historical automated evidence and were not rerun for documentation changes. `docs/evidence/verification.json` remains unchanged as that historical record.

### Unresolved review item R-01 - alert-to-supporting-window display

The project lead reports an **intermittent alert-to-supporting-window display observation**. Record it as unresolved and not independently reproduced. Specific symptom details, frequency, reproduction steps, affected event/window IDs and root cause were not supplied; no cause, severity or fix is inferred. The overall manual acceptance and UI approval are recorded as given, while this observation remains open for a separately authorized review. No implementation change was made or is authorized by this closeout.

### Exceptions retained without waiver

- Three legacy runtime files still differ from the original preservation baseline, as detailed above and in `docs/evidence/preservation.json`. User acceptance does not reset that baseline or turn the full-tree check into a pass. No restoration or overwrite was performed.
- The retained SQLite3.45.3 / GCC16.2 Release compiler warning remains a review item. Passing tests and user acceptance do not prove it harmless; no vendor patch, suppression or dependency change was made.
- University catalog/administrative details, actual team contributions and licensing/publication decisions are separate from product acceptance; no new facts or approvals for those matters were supplied.
