import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from test_collector import BIN, Collector, until


class Monitor:
    def __init__(self, port):
        self.process = subprocess.Popen(
            [str(BIN / "pulsemonitor_v2.exe"), "--port", str(port), "--sample", "1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
            env=dict(os.environ, PATH="C:/msys64/ucrt64/bin;" + os.environ["PATH"]),
        )
        self.messages = queue.Queue()
        self.snapshots = {}
        self.latest = None
        self.ended = set()
        self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()
        assert self.messages.get(timeout=10)["event"] == "ready"

    def _reader(self):
        for line in self.process.stdout:
            message = json.loads(line)
            with self.lock:
                if message.get("event") == "snapshot":
                    sid = message["snapshot_id"]
                    pages = self.snapshots.setdefault(sid, {})
                    pages[message["page"]] = message
                    if len(pages) == message["pages"]:
                        self.latest = dict(pages[0], processes=[p for i in sorted(pages) for p in pages[i]["processes"]])
                        self.snapshots.clear()
                elif message.get("event") == "ended":
                    self.ended.add(message["source"])
                else:
                    self.messages.put(message)

    def row(self, pid, need_cpu=False):
        with self.lock:
            rows = (self.latest or {}).get("processes", [])
            return next((p for p in rows if p["pid"] == pid and (not need_cpu or p["cpu_percent"] is not None)), None)

    def request(self, op, args=None, ok=True):
        rid = str(uuid.uuid4())
        self.process.stdin.write(json.dumps({"v": 1, "id": rid, "op": op, "args": args or {}}) + "\n")
        self.process.stdin.flush()
        reply = self.messages.get(timeout=10)
        assert reply["id"] == rid and reply["ok"] is ok, reply

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


def test_real_process_identity_tracking_and_end(tmp_path):
    collector = Collector(tmp_path)
    monitor = Monitor(collector.port)
    target = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        row = until(lambda: monitor.row(target.pid, need_cpu=True))
        assert row["created"].isdigit() and int(row["created"]) > 2**53
        assert 0 <= row["cpu_percent"] <= 100
        assert row["memory_bytes"] > 0 and not row["tracked"]
        idle = monitor.row(0)
        if idle:
            assert not idle["created"] and idle["cpu_percent"] is None and idle["memory_bytes"] is None
        args = {"pid": row["pid"], "created": row["created"], "label": row["name"]}
        monitor.request("validate", dict(args, created=str(int(row["created"]) + 1)), ok=False)
        monitor.request("validate", args)
        collector.request("track", args)
        monitor.request("track", args)
        until(lambda: (r if (r := monitor.row(target.pid)) and r["tracked"] else None))
        with sqlite3.connect(collector.database) as db:
            until(lambda: db.execute("SELECT count(*) FROM metric_windows mw JOIN sources s ON s.source_id=mw.source_id WHERE s.source_key=?", (row["source"],)).fetchone()[0] >= 2)
        monitor.request("untrack", {"source": row["source"]})
        collector.request("untrack", {"source": row["source"]})
        until(lambda: (r if (r := monitor.row(target.pid)) and not r["tracked"] else None))
        collector.request("track", args)
        monitor.request("track", args)
        target.terminate()
        target.wait(timeout=5)
        until(lambda: row["source"] in monitor.ended)
        collector.request("ended", {"source": row["source"]})
        monitor.request("validate", args, ok=False)
        monitor.request("stop")
        assert monitor.messages.get(timeout=5)["event"] == "stopped"
        assert monitor.process.wait(timeout=5) == 0
        collector.stop()
        with sqlite3.connect(collector.database) as db:
            assert db.execute("SELECT selected,ended_utc_us IS NOT NULL FROM sources WHERE source_key=?", (row["source"],)).fetchone() == (0, 1)
            assert db.execute("SELECT count(*) FROM tracking_intervals WHERE end_reason IN ('ended','untracked')").fetchone()[0] == 2
            assert db.execute("SELECT count(*) FROM metric_windows WHERE name='cpu.percent' AND source_id=(SELECT source_id FROM sources WHERE source_key=?)", (row["source"],)).fetchone()[0] > 0
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        if target.poll() is None:
            target.kill()
            target.wait(timeout=5)
        monitor.close()
        collector.close()
