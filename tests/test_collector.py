"""Functional tests against current-source native binaries; no benchmark workload."""
import json
import os
from pathlib import Path
import queue
import socket
import sqlite3
import subprocess
import threading
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(os.environ.get("PULSE_BIN", ROOT.parent / "PulseMetrics_V2_BUILD/debug/bin"))


class Collector:
    def __init__(self, directory, database=None):
        self.database = database or directory / "metrics.sqlite"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        config = {
            "database": str(self.database), "udp_port": self.port,
            "sample_seconds": 1, "window_seconds": 1, "retention_days": 7,
            "sources": [{"key": "app.fixture", "label": "Functional fixture", "metrics": [
                {"name": "count", "type": "counter", "unit": "count"},
                {"name": "gauge", "type": "gauge", "unit": "unit"},
                {"name": "timer", "type": "timer", "unit": "ms"}]},
                {"key": "app.second", "label": "Independent source", "metrics": [{"name": "count", "type": "counter", "unit": "count"}]}],
        }
        path = directory / "runtime.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        env = dict(os.environ, PATH="C:/msys64/ucrt64/bin;" + os.environ["PATH"])
        self.process = subprocess.Popen(
            [str(BIN / "pulsecollector_v2.exe"), "--config", str(path), "--session", str(uuid.uuid4())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.messages = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        ready = self.messages.get(timeout=10)
        assert ready.get("event") == "ready", ready

    def _reader(self):
        for line in self.process.stdout:
            self.messages.put(json.loads(line))

    def request(self, op, args=None):
        rid = str(uuid.uuid4())
        self.process.stdin.write(json.dumps({"v": 1, "id": rid, "op": op, "args": args or {}}) + "\n")
        self.process.stdin.flush()
        reply = self.messages.get(timeout=15)
        assert reply.get("id") == rid, reply
        assert reply["ok"], reply
        return reply.get("result", {})

    def send(self, text):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(text.encode("ascii"), ("127.0.0.1", self.port))

    def stop(self, clean=True):
        self.request("stop")
        done = self.messages.get(timeout=15)
        assert done.get("event") == "stopped", done
        assert done["clean"] is clean, done
        assert self.process.wait(timeout=5) == (0 if clean else 1)
        return done

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


def until(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("condition did not become true before deadline")


def test_arithmetic_validation_restart(tmp_path):
    app = Collector(tmp_path)
    try:
        app.send("app.fixture/count:2|c\napp.fixture/count:3|c\napp.fixture/gauge:4|g\napp.fixture/gauge:9|g\napp.fixture/timer:10|ms\napp.fixture/timer:30|ms\napp.fixture/timer:50|ms")
        app.send("app.fixture/count:8|g\napp.fixture/count:-1|c\napp.fixture/timer:nan|ms\napp.fixture/gauge:1junk|g\napp.unknown/count:1|c")
        until(lambda: app.request("status")["lines_received"] == 12)
        health = app.request("status")
        assert (health["accepted"], health["rejected"]) == (7, 5)
        app.stop()
        with sqlite3.connect(app.database) as db:
            rows = dict((name, (n, total, low, high)) for name, n, total, low, high in db.execute(
                "SELECT name,sum(sample_count),sum(sample_sum),min(sample_min),max(sample_max) FROM metric_windows GROUP BY name"))
            assert rows == {"count": (2, 5, 2, 3), "gauge": (2, 13, 4, 9), "timer": (3, 90, 10, 50)}
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        app.close()
    restart = Collector(tmp_path, app.database)
    try:
        restart.stop()
        with sqlite3.connect(app.database) as db:
            assert db.execute("SELECT count(*) FROM sessions WHERE state='clean'").fetchone()[0] == 2
            assert db.execute("SELECT sum(sample_count) FROM aggregates").fetchone()[0] == 7
    finally:
        restart.close()


def test_locked_database_capacity_and_recovery(tmp_path):
    app = Collector(tmp_path)
    lock = sqlite3.connect(app.database, isolation_level=None)
    try:
        lock.execute("BEGIN IMMEDIATE")
        for _ in range(7):
            app.send("app.fixture/count:1|c")
            time.sleep(1.03)
        frozen = until(lambda: (s if (s := app.request("status"))["backpressure"] else None))
        assert frozen["pending_batches"] == 6
        assert frozen["queued_batches"] + frozen["inflight_batches"] == 6
        assert frozen["inflight_batches"] == 1
        assert frozen["accepted"] == 7 and frozen["uncommitted_samples"] == 7
        assert frozen["write_failures"] > 0 and not frozen["write_healthy"]
        app.send("app.fixture/count:1|c")
        until(lambda: app.request("status")["known_dropped"] == 1)
        lock.execute("ROLLBACK")
        until(lambda: app.request("status")["uncommitted_samples"] == 0)
        done = app.stop()
        assert done["accepted"] == 7 and done["uncommitted_samples"] == 0
        with sqlite3.connect(app.database) as db:
            assert db.execute("SELECT sum(sample_count),sum(sample_sum) FROM aggregates").fetchone() == (7, 7)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        lock.close()
        app.close()


def test_failed_shutdown_reports_uncommitted(tmp_path):
    app = Collector(tmp_path)
    lock = sqlite3.connect(app.database, isolation_level=None)
    try:
        lock.execute("BEGIN IMMEDIATE")
        app.send("app.fixture/count:1|c")
        until(lambda: app.request("status")["accepted"] == 1)
        done = app.stop(clean=False)
        assert done["uncommitted_samples"] == 1
        assert done["write_failures"] > 0
    finally:
        lock.close()
        app.close()


def test_sources_and_bounded_control_framing(tmp_path):
    app = Collector(tmp_path)
    try:
        app.send("app.fixture/count:5|c\napp.second/count:7|c")
        until(lambda: app.request("status")["accepted"] == 2)
        app.send("x" * 1201)
        app.send("app.fixture/count:1|c\n" * 17)
        app.send("")
        until(lambda: app.request("status")["datagrams_rejected"] == 3)
        app.process.stdin.write("x" * 65537 + "\n")
        app.process.stdin.flush()
        assert app.messages.get(timeout=5)["ok"] is False
        app.process.stdin.write('{"v":1,"id":"bad","op":"status"}\x00junk\n')
        app.process.stdin.flush()
        assert app.messages.get(timeout=5)["ok"] is False
        rid = str(uuid.uuid4())
        packet = json.dumps({"v": 1, "id": rid, "op": "status"}) + "\n"
        app.process.stdin.write(packet[:10])
        app.process.stdin.flush()
        app.process.stdin.write(packet[10:])
        app.process.stdin.flush()
        assert app.messages.get(timeout=5)["id"] == rid
        app.stop()
        with sqlite3.connect(app.database) as db:
            assert dict(db.execute("SELECT s.source_key,sum(a.sample_sum) FROM aggregates a JOIN metrics m USING(metric_id) JOIN sources s USING(source_id) GROUP BY s.source_key")) == {"app.fixture": 5, "app.second": 7}
    finally:
        app.close()


def test_control_eof_commits_before_exit(tmp_path):
    app = Collector(tmp_path)
    try:
        app.send("app.fixture/count:1|c")
        until(lambda: app.request("status")["accepted"] == 1)
        app.process.stdin.close()
        final = app.messages.get(timeout=15)
        assert final["event"] == "stopped" and final["clean"]
        assert final["uncommitted_samples"] == 0
        assert app.process.wait(timeout=5) == 0
    finally:
        app.close()
