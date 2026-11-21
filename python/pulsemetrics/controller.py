"""One owner for native children, Streamlit, settings and local control."""
from collections import OrderedDict
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

from . import ipc
from .child import Child
from .data import Data
from .windows import Job, lock_runtime, owns_listener

ROOT = Path(__file__).resolve().parents[2]


def validate_settings(config):
    bounds = {"sample_seconds": (1, 60), "window_seconds": (1, 60), "refresh_seconds": (1, 60),
              "retention_days": (1, 30), "udp_port": (1024, 65535), "ui_port": (1024, 65535)}
    for key, (low, high) in bounds.items():
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    if config["window_seconds"] < config["sample_seconds"]:
        raise ValueError("Aggregation window must be at least the sampling interval")


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Controller:
    def __init__(self, directory, binary_dir):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = lock_runtime(self.directory / "application.lock")
        self.job = None
        self.server = None
        self.collector = self.monitor = self.ui = None
        self.closed = False
        self.state = "starting"
        self.exit_result = None
        self.exit_seen = False
        self.exit_deadline = None
        self.shutdown_thread = None
        self.snapshot_lock = threading.Lock()
        self.snapshot = None
        self.snapshot_pages = {}
        self.ended = queue.Queue(maxsize=100)
        self.pending_ended = set()
        self.mutations = OrderedDict()
        self.monitor_error = None
        try:
            self.logger = logging.getLogger(f"pulsemetrics.{uuid.uuid4()}")
            self.logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(self.directory / "components.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
            config_path = self.directory / "config.json"
            if not config_path.exists():
                atomic_json(config_path, json.loads((ROOT / "config/example.json").read_text(encoding="utf-8")))
            if config_path.stat().st_size > 65536:
                raise ValueError("Configuration exceeds 64 KiB")
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
            validate_settings(self.config)
            self.saved_config = dict(self.config)
            self.database = self.directory / "metrics.sqlite"
            self.data = Data(self.database)
            self.binary_dir = Path(binary_dir).resolve()
            self.env = dict(os.environ)
            self.env["PATH"] = "C:/msys64/ucrt64/bin;" + self.env.get("PATH", "")
            self.env["PYTHONPATH"] = str(ROOT / "python") + os.pathsep + self.env.get("PYTHONPATH", "")
            self.job = Job()
            self.server = ipc.Server(self.handle)
        except Exception:
            self.close()
            raise

    def native_start(self):
        runtime = dict(self.config, database=str(self.database))
        atomic_json(self.directory / "collector.json", runtime)
        self.collector = Child([str(self.binary_dir / "pulsecollector_v2.exe"), "--config", str(self.directory / "collector.json"), "--session", str(uuid.uuid4())], self.env, self.job, self.logger)
        self.collector.wait_ready()
        try:
            self.monitor = Child([str(self.binary_dir / "pulsemonitor_v2.exe"), "--port", str(self.config["udp_port"]), "--sample", str(self.config["sample_seconds"])], self.env, self.job, self.logger, self.monitor_event)
            self.monitor.wait_ready()
            # Selection is intent; restore only an independently revalidated instance.
            for source in self.data.sources():
                if source["kind"] == "process" and source["selected"]:
                    args = {"pid": source["pid"], "created": str(source["creation_filetime"]), "label": source["display_name"]}
                    try:
                        self.track(args)
                    except (RuntimeError, TimeoutError, OSError):
                        # Access denied is not proof of termination. Preserve intent.
                        self.logger.warning("Saved selection %s could not be revalidated", source["source_key"])
        except (RuntimeError, TimeoutError, OSError) as exc:
            self.monitor_error = str(exc)
            self.logger.error("Live monitoring unavailable: %s", exc)
        self.state = "running"

    def monitor_event(self, message):
        if message.get("event") == "ended":
            try:
                self.ended.put_nowait(message["source"])
            except queue.Full:
                self.monitor_error = "Process-end notification queue is full; lifecycle state is uncertain"
            return
        if message.get("event") != "snapshot":
            return
        page, pages = message.get("page"), message.get("pages")
        if not isinstance(page, int) or not isinstance(pages, int) or not 0 <= page < pages <= 400:
            self.monitor_error = "Invalid process snapshot page"
            return
        with self.snapshot_lock:
            sid = message["snapshot_id"]
            if self.snapshot_pages.get("id") != sid:
                self.snapshot_pages = {"id": sid, "pages": {}}
            parts = self.snapshot_pages["pages"]
            parts[page] = message
            if len(parts) == pages:
                self.snapshot = dict(parts[0], processes=[row for i in range(pages) for row in parts[i]["processes"]], received_mono=time.monotonic())
                self.snapshot_pages = {}

    def ui_start(self, open_browser=True):
        port = self.config["ui_port"]
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("127.0.0.1", port))
        env = dict(self.env, PULSE_PIPE=self.server.name, PULSE_DATABASE=str(self.database),
                   PULSE_REFRESH=str(self.config["refresh_seconds"]), STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
        command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "python/pulsemetrics/ui/app.py"),
                   "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
                   "--server.fileWatcherType=none", "--browser.gatherUsageStats=false", "--client.toolbarMode=minimal",
                   "--theme.base=dark", "--theme.primaryColor=#2DE0C4", "--theme.backgroundColor=#050A14",
                   "--theme.secondaryBackgroundColor=#0B1424", "--theme.textColor=#E6EEFB",
                   "--theme.font=sans-serif"]
        self.ui = subprocess.Popen(command, env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        self.job.own(self.ui)
        threading.Thread(target=self._ui_log, daemon=True).start()
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.ui.poll() is not None:
                raise RuntimeError("Streamlit server exited during startup")
            if owns_listener(self.ui.pid, port, self.job.handle):
                try:
                    with urllib.request.urlopen(url + "/_stcore/health", timeout=0.5) as response:
                        if response.status == 200:
                            if open_browser:
                                webbrowser.open(url)
                            return url
                except OSError:
                    pass
            time.sleep(0.1)
        raise TimeoutError("Owned Streamlit server did not become healthy within 30 seconds")

    def _ui_log(self):
        while line := self.ui.stdout.readline(4096):
            self.logger.info("UI: %s", line.rstrip())

    def track(self, args):
        if not self.monitor or self.monitor.process.poll() is not None:
            raise RuntimeError("Native monitor is unavailable")
        self.monitor.request("validate", args)
        self.collector.request("track", args)
        try:
            self.monitor.request("track", args)
        except Exception:
            self.collector.request("untrack", {"source": f"p.{args['pid']}.{args['created']}"})
            raise

    def status(self):
        with self.snapshot_lock:
            snapshot = self.snapshot
            live = {key: value for key, value in (snapshot or {}).items() if key not in ("processes", "received_mono")}
            rows = (snapshot or {}).get("processes", [])
            live["discovered"] = len(rows)
            live["tracked"] = sum(row["tracked"] for row in rows)
            live["age_seconds"] = time.monotonic() - snapshot["received_mono"] if snapshot else None
            live["top"] = sorted((r for r in rows if r["tracked"] and r["cpu_percent"] is not None), key=lambda r: r["cpu_percent"], reverse=True)[:5]
        health = {}
        if self.state == "running":
            try:
                health = self.collector.request("status", timeout=2)
            except (RuntimeError, TimeoutError, OSError) as exc:
                health = {"state": "unavailable", "last_error": str(exc)}
        return {"state": self.state, "live": live, "collector": health, "monitor_error": self.monitor_error,
                "settings": {k: v for k, v in self.saved_config.items() if k != "sources"},
                "restart_required": any(self.config[k] != self.saved_config[k] for k in self.config if k not in ("sources", "refresh_seconds")),
                "exit_result": self.exit_result}

    def dispatch(self, op, args, rid):
        if op == "status":
            return self.status()
        if op == "exit_result_seen":
            self.exit_seen = True
            return {}
        if op == "exit":
            if self.state == "running":
                self.state = "stopping"
                self.shutdown_thread = threading.Thread(target=self.shutdown_native, daemon=True)
                self.shutdown_thread.start()
            return {"state": self.state}
        if self.state != "running":
            raise RuntimeError("Application is stopping; commands are disabled")
        if op == "list_processes":
            with self.snapshot_lock:
                rows = list((self.snapshot or {}).get("processes", []))
            search = str(args.get("search", "")).casefold()[:260]
            rows = [r for r in rows if search in r["name"].casefold() or search in str(r["pid"])]
            key = args.get("sort", "cpu_percent")
            if key not in ("name", "pid", "cpu_percent", "memory_bytes"):
                raise ValueError("Invalid process sort")
            rows.sort(key=lambda r: (r[key] is not None, r[key] if r[key] is not None else -1), reverse=key != "name")
            start = max(0, min(int(args.get("offset", 0)), 10000))
            return {"total": len(rows), "rows": rows[start:start + 25]}
        if op == "track":
            self.track(args)
        elif op == "untrack":
            self.monitor.request("untrack", args)
            self.collector.request("untrack", args)
        elif op in ("add_rule", "disable_rule"):
            self.collector.request(op, args, request_id=rid)
        elif op == "save_settings":
            allowed = {"sample_seconds", "window_seconds", "refresh_seconds", "retention_days", "udp_port", "ui_port"}
            if set(args) - allowed:
                raise ValueError("Unknown setting")
            candidate = dict(self.saved_config, **args)
            validate_settings(candidate)
            atomic_json(self.directory / "config.json", candidate)
            self.saved_config = candidate
            return {"message": "Saved. Refresh applies now; collection settings apply after restart."}
        else:
            raise ValueError("Unsupported operation")
        return {"message": "Applied"}

    def handle(self, command):
        rid = command.get("id", "")
        response = {"v": 1, "id": rid, "ok": False}
        try:
            if command.get("v") != 1 or not isinstance(rid, str) or str(uuid.UUID(rid)) != rid:
                raise ValueError("Expected version 1 and a UUID request ID")
            op, args = command.get("op"), command.get("args", {})
            if not isinstance(args, dict):
                raise ValueError("args must be an object")
            mutation = op not in ("status", "list_processes", "exit_result_seen")
            signature = json.dumps([op, args], sort_keys=True, allow_nan=False)
            if mutation and rid in self.mutations:
                previous, reply = self.mutations[rid]
                if previous != signature:
                    raise ValueError("Request ID was reused with different content")
                return reply
            result = self.dispatch(op, args, rid)
            response.update(ok=True, result=result)
            if mutation:
                self.mutations[rid] = (signature, response)
                if len(self.mutations) > 256:
                    self.mutations.popitem(last=False)
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, TimeoutError) as exc:
            response["message"] = str(exc)
        return response

    def shutdown_native(self):
        errors = []
        for child in (self.monitor, self.collector):
            if child:
                try:
                    child.stop()
                except (RuntimeError, TimeoutError, OSError) as exc:
                    errors.append(str(exc))
        self.exit_result = {"clean": not errors, "errors": errors, "collector": self.collector.final if self.collector else None}
        try:
            atomic_json(self.directory / "last_shutdown.json", self.exit_result)
        except OSError as exc:
            errors.append(f"Could not save shutdown report: {exc}")
            self.exit_result["clean"] = False
        self.logger.info("Shutdown result: %s", self.exit_result)
        self.state = "stopped"
        self.exit_deadline = time.monotonic() + 20

    def serve(self):
        while not (self.state == "stopped" and (self.exit_seen or time.monotonic() >= self.exit_deadline)):
            if self.state == "running":
                while not self.ended.empty():
                    self.pending_ended.add(self.ended.get_nowait())
                for source in list(self.pending_ended):
                    try:
                        self.collector.request("ended", {"source": source}, timeout=1)
                        self.pending_ended.remove(source)
                    except (RuntimeError, TimeoutError, OSError):
                        break
                if self.ui and self.ui.poll() is not None:
                    self.state = "stopping"
                    self.shutdown_native()
                    self.exit_seen = True
            self.server.once()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.shutdown_thread:
            self.shutdown_thread.join(timeout=20)
        elif self.collector and self.state != "stopped":
            self.shutdown_native()
        if self.job:
            self.job.close()
        for child in (self.monitor, self.collector):
            if child:
                child.close()
        if self.ui:
            self.ui.wait(timeout=5)
            self.ui.stdout.close()
        if self.server:
            self.server.close()
        ipc.close(self.lock)
        if hasattr(self, "logger"):
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)
