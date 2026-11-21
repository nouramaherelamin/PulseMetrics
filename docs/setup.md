# Setup and troubleshooting

## Verified environment

Windows 11 x64 build 26200; Python 3.14.6 (Anaconda); MSYS2 UCRT64 GCC16.2.0, CMake/CTest4.5.0, Ninja1.13.2; Streamlit1.58.0, Plotly6.7.0, Pandas3.0.3, pytest9.0.3. Native SQLite3.45.3 and the received compact cJSON adaptation are vendored. No GTK/Cairo, psutil, ORM, pywin32, web application framework or REST API is used by the project. Streamlit's own transitive dependencies are listed in the runtime lock; those do not constitute additional application services.

The original toolchain acquisition blocker is resolved. No dependency installation or system-setting change was performed during this resumed implementation. Builds use a process-local UCRT64 PATH.

## Reproduce on another Windows machine

1. Install official MSYS2 from `https://www.msys2.org/`. In its UCRT64 terminal, update with `pacman -Syu` (reopen/update again if instructed), then install:

   ```text
   pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja
   ```

2. Install a compatible x64 Python. Python3.14.6 is the tested interpreter. Create an isolated environment outside source and install the pinned Windows runtime dependency closure:

   ```powershell
   python -m venv ..\PulseMetrics_V2_ENV
   ..\PulseMetrics_V2_ENV\Scripts\python.exe -m pip install -r requirements.lock.txt
   ..\PulseMetrics_V2_ENV\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

   These are manual setup instructions, not installations this agent performed. The lock records the installed package set; this environment did not verify a fresh package download or offline wheel availability. Use official PyPI packages or verified offline wheels. No activation or persistent PATH change is necessary.

3. From the repository, use that environment's Python with `scripts/build.py`, then `scripts/launch.py`. The build helper sets explicit GCC/Ninja paths and places Debug outputs in `../PulseMetrics_V2_BUILD/debug`. `--configuration Release` selects the separate Release tree. `--toolchain` changes the build-tool directory when needed. The supplied installation path is `C:/msys64/ucrt64/bin`.
4. `python scripts/verify.py --configuration Release` runs CMake, native CTest and all pytest cases against the selected freshly built binaries. It writes a unique evidence directory outside source.

SQLite is compiled into the collector. There is no SQLite server or GTK DLL setup. Python dependencies must be installed before an offline launch; the launcher never invokes pip or pacman.

## Data and configuration

`--data-dir <directory>` selects an independent runtime. Default: `%LOCALAPPDATA%/PulseMetricsV2`. It contains `config.json`, generated native configuration, `metrics.sqlite`/WAL/SHM, bounded component logs and `last_shutdown.json`. A Win32 exclusive file handle prevents a second controller using the same directory. Different runtime directories still require distinct UDP/UI ports.

Settings validate sampling/window/refresh in1-60seconds, retention1-30days, and ports1024-65535. Window >= sampling. Dashboard refresh applies after the settings rerun; collection, retention and ports require an explicit Exit and relaunch. External sources are declared in the runtime JSON before launch; see `config/example.json`. Do not change source types/units in place: give a changed contract a new metric name.

For a stopped backup, use Exit, verify `last_shutdown.json` reports clean, then copy the complete runtime directory. Do not copy only the main SQLite file while the collector is running. No V1 import is supported; preserve V1 data separately.

## Troubleshooting

| Symptom | Action |
|---|---|
| Cannot locate gcc/cmake/ninja | Verify official UCRT64 binaries at C:/msys64/ucrt64/bin. Run the Python build helper; do not reuse a legacy CMake cache. |
| PowerShell blocks .ps1 | Use the Python entry points. No execution-policy change is needed. |
| Port already in use | Stop the conflicting application or choose another local port in runtime config, then restart. The controller does not kill unrelated processes or accept another server as ready. |
| Runtime already in use | Exit its existing controller. A stale lock file alone is harmless; ownership is the live Windows handle. |
| Database startup failure | Inspect components.log. Unsupported schema/corruption fails explicitly. Preserve the files; use a separate new data directory to investigate. |
| Pending batches/write errors | Inspect Health. At six pending batches the active store freezes; newly received lines are refused and counted. Accepted observations remain in memory for retry. |
| Failed shutdown | Inspect last_shutdown.json and logs. A non-clean result may contain accepted-but-uncommitted counts. Forced termination cannot guarantee persistence of those values. |
| Process access unavailable | No elevation is required. Keep the unavailable state, retry when accessible, or remove its saved selection. PID alone is never a safe identity. |
| Clock warning | History keeps actual session timestamps; lifecycle uses session order. Retention pauses for that session. Correct the clock outside the application, then restart. |
| Server healthy but no browser | Open the printed loopback URL. Server readiness does not depend on a browser client. |
| GUI automation cannot capture | Complete docs/testing.md manually on the interactive desktop. AppTest passes do not establish pixel layout or browser behavior. |

Runtime logs rotate at5MiB with three backups. Retention removes eligible history in bounded writer transactions; it is not a hard disk-size limit. Open alert evidence and selected identities may outlive expired windows.
