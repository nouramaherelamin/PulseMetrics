# Course technical report and requirements coverage

## Actual product and evidence basis

PulseMetrics V2 implements a genuine Project47-style metrics daemon plus a local Windows performance-history product. Approved C17 replaces the original approved C++ choice; native Win32 monitoring replaces the original Python monitor proposal; Streamlit/Plotly replaces the received GTK presentation. Core receiving, parsing, validation, aggregation, synchronization and persistence remain native C. Counters/gauges/measured timers are demonstrated by an independent C sender, not fabricated process response times.

The university catalog was not supplied. `[U]` below means the supplied16-page v1.1 specification's interpretation of university requirements, previously reviewed in full. `[A]` denotes approved product decisions, `[P]` engineering defaults, `[F]` deferred/excluded scope. Latest project-lead V2 decisions supersede conflicting legacy product/technology decisions. This report documents actual code and results, not a university compliance certificate.

## Systems and data implementation

Win32 OS interactions include Winsock UDP/socket lifetime, QPC/UTC clocks, Toolhelp process snapshots, process-time and memory queries, critical sections, thread handles/events, process exit observation, current-user named-pipe ACLs, exclusive runtime-file ownership and Job Objects. SQLite WAL transactions provide the sole persistence writer; Python uses short-lived mode=ro/query_only connections. The controller owns children outside Streamlit reruns. See `architecture.md` and `database/schema.sql` for contracts, ERD, resource bounds and lifecycle corrections A-E.

The pipeline is external sender/native monitor -> loopback UDP -> C validation/store -> immutable bounded batches -> SQLite aggregates/alerts/health -> read-only Python -> four functional UI pages. Original unbounded/name-grouped/false-zero behavior is replaced with registered sources, exact process instances and explicit missing observations. Raw datagrams are not stored; window statistics and receipt bounds are traceable to accepted observations, and accepted is explicitly distinct from durable.

## Requirements matrix

| Requirement | Classification | Implementation and evidence / remaining limit |
|---|---|---|
| Project47 counter/gauge/timer daemon | [U] | C protocol/store/engine and measured sender; native arithmetic and real UDP/integration passed |
| Source code/build/test package | [U] | Clean source, vendor notices, CMake/Python entry points, dependency lock, actual hashed Release verification and source-only archive |
| Functional GUI | [U] | Real Overview/Explorer/Analytics/Time Machine AppTest controls passed; project-lead manual acceptance and UI approval reported; distinct from automated evidence |
| Course report | [U] | This report plus architecture/setup/testing/user guide; actual roster/contributions and final screenshots still required |
| Team8-10 / deadline | [U] | Administrative input absent; no roster, deadline or work credit invented |
| FR-01 discovery | [A] | Toolhelp + bounded paged snapshots/search/sort; real process test passed |
| FR-02 system CPU/RAM | [A] | Native delta/physical-memory measurements, live sample time; real Overview passed |
| FR-03 track/untrack | [A] | Revalidate/commit/enable with acknowledgement; actual UI/native test passed |
| FR-04 lifecycle/PID reuse | [A] | PID+creation FILETIME, signaled handles, saved uncertain intent; mismatch fixture and real termination passed. Actual OS PID recycling not forced. |
| FR-05 three metric types | [U] | Genuine source-specific C processing and measured sender verified |
| FR-06 validation | [A], supports[U] | Exact grammar, finite/range/type/unit/identity/length bounds; rejection fixtures passed |
| FR-07 windows | [U] | Actual elapsed/QPC, complete snapshots and type math; native tests passed |
| FR-08 history | [A] | Checked WAL transactions/retry/restart; lock/failure/history tests passed |
| FR-09 GUI data | [U] | Read-only real SQLite + live IPC, tested with native processes and sender |
| FR-10 four screens | [A], GUI[U] | Four screens implemented/functionally tested; current UI/UX explicitly approved by the project lead |
| FR-11 Time Machine | [A] | Saved IDs/UTC, previous/next, gaps and compatible comparisons; functional tests passed; manual Time Machine/history comparisons reported passed |
| FR-12 alerts | [A] | Native immutable rules, independent events, missing-data unresolved, breach/recovery/restart/retention tested |
| FR-13 insights | [A] | Actual threshold evidence and same-session observed memory endpoint changes; weighted math tests passed |
| FR-14 health | [A] | Live receiver/accepted/rejected/drop/write/pending/commit/clock states independent of DB readability; failure tests passed |
| FR-15 error/missing states | [A] | Empty/stale/unavailable/ended/error paths implemented; backend/AppTest checks passed; overall manual checklist reported passed (detailed execution log not supplied) |
| FR-16 Exit/restart | [A] | Ordered stop/drain/result/Job cleanup; clean, failed-drain, EOF, reaping and restart tests passed |
| FR-17 offline | [A] | No required application external service; local destinations/assets and telemetry disabled. Offline operation and offline startup reported passed by the project lead. |
| FR-18 core demonstration | [A], evidence[U] | Actual C sender observations -> DB/UI/alert/history verified; manual project acceptance reported complete |
| 5/10/5seconds and7days | [P], approved initial defaults | Config example, validated bounds and restart semantics implemented |
| Premium navy desktop UX | [A] | Previous purple/cyan UI/UX was approved by the project lead. A later PC-monitoring redesign (navy/cyan/teal, see ui-redesign.md) has automated/logic checks only and awaits project-lead acceptance; no independent screenshot evidence claimed |
| Cloud, AI, REST, extra frontend, demo modes, advanced benchmarks | [F]/explicit exclusions | Not implemented. Streamlit's own transitive libraries are dependencies, not additional application services. |

## Original scenarios T-01 through T-15

T-01 valid types, T-02 arithmetic, T-03 invalid input, T-04 independent sources, T-05 bounded buffering, T-06 termination, T-07 inaccessible identity, T-08 PID identity mismatch, T-09 empty/stale backend states, T-10 measured-sender threshold, T-11 gap-aware historical queries, T-12 database refusal/recovery and T-13 shutdown/restart have automated evidence in the native suites and `tests/`. The project lead now reports all 15 manual checklist items passed, including the historical/alert workflows and offline operation/startup. This user-reported acceptance is separate from the automated evidence; individual execution details were not supplied. T-15 advanced quantitative load target is superseded by explicit scope exclusion; deterministic capacity tests remain. See testing.md for exact commands and limitations.

## Audit-finding resolution map

These are V2 resolutions; they do not retroactively change the received implementation's audit findings.

| Original finding | V2 disposition / verification |
|---|---|
| F01 parsing, F06 collisions, F22 truncation | Strict registered source/name/type/unit grammar and128-byte boundary; native and UDP tests |
| F02 snapshot starvation, F03 unbounded buffering | Complete1,024-series snapshot and six immutable pending batches; independent capacity/backpressure recovery |
| F04 discarded write failures | Retry same immutable batch until checked COMMIT; query-only/lock and failed-drain tests |
| F05 wrong denominator, F13 timestamps | Actual QPC interval, receipt-time semantics and session-order clock policy; arithmetic/rollback fixtures |
| F07 opt-in identity, F08 PID/false zeros | Exact instances, selected-only history, explicit warmup/unavailable; real monitor/controller tests |
| F09 missing journey, F10 invented history | Four pages and real stored windows; AppTest passed; project-lead manual acceptance reported complete; intermittent alert-window display observation remains R-01 in testing.md |
| F11 misleading connection | Live C health separate from persistence/last receipt/commit; failure evidence |
| F12 unsafe shutdown | Owned children, producer-first stop, bounded collector drain, explicit final event, Job fallback; tests |
| F14 retention | Bounded writer cleanup, surviving open-alert evidence and FK integrity; native retention fixture |
| F15 alerts/restart/collisions | UUID rules, unique open events, native recovery and missing-data policy; fixtures |
| F16 fabricated demo | Standalone measured C checksum sender; real process end-to-end verification |
| F17 mixed units/counts | Typed units and unique sources; CPU normalization, binary memory labels, honest timer semantics |
| F18 destructive packaging | New unique Git source archive, no runtime deletion or bundled history; archive/sentinel checks |
| F19 hidden DAL failures | mode=ro/query_only and explicit errors; read-only/missing-schema tests |
| F20 config failures | Atomic replace and bounds/effective-vs-saved state; refusal/idempotency tests |
| F21 unproven build | Fresh Debug/Release with current-source/binary hashes; vendor warning recorded |
| F23 remote destination | Native UDP destinations hardcoded loopback; no editable host |
| F24 GTK ownership/blocking | GTK absent; bounded native control/read queries and external controller ownership; lifecycle tests |

## Readiness and remaining work

Automated functional implementation gates passed; the project lead reports completion of manual graphical/offline acceptance and explicitly approves the current UI/UX. The intermittent alert-to-supporting-window display observation remains unresolved (R-01 in testing.md). The retained SQLite warning and dependency maintenance need review before wider release. Hardware coverage is one Windows11 x64 environment; unsupported multi-group CPU returns unavailable. Tests do not establish all OS versions, machine capacities, hostile-local-user security or maximum throughput.

The specification, all approved design/audit baselines and1,076 of1,079 received files match their original hashes. Three received legacy runtime files differ, as detailed below; full-tree preservation is not a pass. No production runtime database/process-history file enters Git or the source archive.

Meaningful remaining team responsibilities for8-10 actual members: native review and regression ownership; process-monitor/platform validation; persistence/retention review; controller/deployment; Python analytics; review of the approved UI/accessibility (changes require separate authorization); integration/offline QA; user/build documentation; course presentation; evidence and release review (combine adjacent areas for8). These are proposed ownership areas, not claims about work already performed. Each member's actual artifacts, reviews and tests must be recorded honestly by the project lead.

Before submission: confirm actual catalog requirements and deadline; supply roster/contribution evidence; retain the user-reported manual acceptance record and supply genuine screenshots if required by the course; approve first-party licensing/publication policy. No remote repository has been created or published by this task.

Preservation exception at final acceptance: three legacy runtime files (the received dist database and collector/monitor logs) differ from the original baseline; their observed write time is2026-11-16T12:25:43Z. All other received files, specification, approved design and audit baselines match. The actor is unverified; no original was restored or overwritten. Full-tree preservation is not a pass and requires project-lead acknowledgement/investigation. See testing.md and the preservation manifest.
