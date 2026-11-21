"""Synthetic fixtures for UI regression tests ONLY.

Nothing here is shipped to the running application: it builds a throwaway SQLite database from
database/schema.sql and a controller-status reply with made-up numbers so the redesigned pages can be
rendered deterministically. Values are never displayed outside the test run.
"""
import math
from pathlib import Path
import os
import sqlite3
import time
import uuid

SCHEMA = Path(__file__).resolve().parents[1] / "database" / "schema.sql"


def make_db(path, with_gap=True):
    if os.path.exists(path): os.remove(path)
    db = sqlite3.connect(path); db.executescript(open(SCHEMA, encoding="utf-8").read())
    now = int(time.time() * 1e6); n = 200; start = now - n * 10_000_000 - 5_000_000
    db.execute("INSERT INTO sessions(session_id,started_utc_us,state,window_seconds,sample_seconds,config_revision) VALUES('sess-1',?,'running',10,5,1)", (start,))
    db.execute("INSERT INTO sources(source_id,source_key,kind,display_name,first_seen_utc_us,last_seen_utc_us) VALUES(1,'system','system','This computer',?,?)", (start, now))
    db.execute("INSERT INTO sources(source_id,source_key,kind,display_name,first_seen_utc_us,last_seen_utc_us) VALUES(2,'app.sender','application','Measured metric sender',?,?)", (start, now))
    M = [(1, 1, "cpu.percent", "gauge", "percent"), (2, 1, "memory.used", "gauge", "bytes"), (3, 1, "memory.total", "gauge", "bytes"),
         (4, 1, "memory.available", "gauge", "bytes"), (5, 1, "memory.percent", "gauge", "percent"), (6, 2, "operations", "counter", "count")]
    db.executemany("INSERT INTO metrics(metric_id,source_id,name,kind,unit) VALUES(?,?,?,?,?)", M)
    total = 33662803968
    for i in range(n):
        if with_gap and 120 <= i < 126: continue
        s = start + i * 10_000_000; e = s + 10_008_000
        cur = db.execute("INSERT INTO windows(session_id,sequence,start_utc_us,end_utc_us,elapsed_us,partial,committed_utc_us) VALUES('sess-1',?,?,?,?,0,?)", (i, s, e, e - s, e))
        w = cur.lastrowid; cpu = 18 + 10 * math.sin(i / 6); used = total * (0.42 + 0.02 * math.sin(i / 30))
        vals = {1: cpu, 2: used, 3: total, 4: total - used, 5: used * 100 / total}
        for mid, v in vals.items():
            db.execute("INSERT INTO aggregates VALUES(?,?,?,?,?,?,?,?,?,?)", (w, mid, "gauge", 2, 2 * v, v * .9, v * 1.1, v, s + 1000, s + 6000))
        if i % 40 == 5:
            db.execute("INSERT INTO aggregates VALUES(?,?,?,?,?,?,?,?,?,?)", (w, 6, "counter", 5, 5, 1, 1, 1, s + 1000, s + 6000))
        db.execute("INSERT INTO health_samples VALUES(?,?,?,?,?,?,?,?,?,?,?,0)", (w, 1, 0, 2, 2, 0, 0, 0, 0, s + 1000, e))
    rid1, rid2 = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute("INSERT INTO alert_rules VALUES(?,1,'CPU Alert Test','last','gt',50,'critical',1,?)", (rid1, start))
    db.execute("INSERT INTO alert_rules VALUES(?,1,'CPU Warn Test','last','gt',40,'warning',0,?)", (rid2, start))
    ow = db.execute("SELECT window_id FROM windows ORDER BY window_id DESC LIMIT 1").fetchone()[0]
    db.execute("INSERT INTO alert_events(rule_id,opened_session_order,last_session_order,opened_utc_us,last_evaluated_utc_us,first_window_id,last_window_id,opening_value,last_value) VALUES(?,1,1,?,?,?,?,60,61)", (rid1, now - 100_000_000, now - 10_000_000, ow, ow))
    db.execute("INSERT INTO alert_events(rule_id,opened_session_order,last_session_order,closed_session_order,opened_utc_us,last_evaluated_utc_us,closed_utc_us,close_reason,first_window_id,last_window_id,opening_value,last_value) VALUES(?,1,1,1,?,?,?,'recovered',NULL,NULL,45,12)", (rid2, now - 900_000_000, now - 800_000_000, now - 800_000_000))
    db.commit(); db.close(); return path



def status_state(now_us=None, age=1.2, cpu=16.4, healthy=True):
    now_us = now_us or int(time.time() * 1e6)
    gib = 2 ** 30
    system = dict(cpu_percent=cpu, memory_used_bytes=12.8 * gib, memory_total_bytes=31.35 * gib, memory_percent=40.8, logical_processors=16, cpu_topology_supported=True)
    return dict(state="running", settings=dict(sample_seconds=5, window_seconds=10, refresh_seconds=5, retention_days=7, udp_port=8125, ui_port=8501),
                restart_required=False, exit_result=None, monitor_error=None,
                live=dict(snapshot_id=3, page=0, pages=1, sampled_at_us=now_us, complete=True, truncated=False, system=system, discovered=337, tracked=1, age_seconds=age,
                          top=[dict(name="python.exe", pid=18656, cpu_percent=0.4, memory_bytes=150.7 * 2**20)]),
                collector=dict(state="running", accepted=2139, rejected=0, known_dropped=0, pending_batches=0, write_healthy=healthy, last_error="" if healthy else "database is locked",
                               last_commit_us=now_us - 6_000_000, clock_warning=False, backpressure=False))
