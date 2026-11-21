"""Short-lived read-only SQLite access. Native collector is the sole writer."""
from contextlib import closing
from pathlib import Path
import sqlite3


class Data:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def query(self, sql, parameters=()):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0.5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA foreign_keys=ON")
            return [dict(row) for row in db.execute(sql, parameters)]

    def sources(self):
        return self.query("SELECT * FROM sources ORDER BY kind,display_name,source_id")

    def metrics(self, source_id=None):
        return self.query("SELECT m.*,s.display_name,s.source_key FROM metrics m JOIN sources s USING(source_id) WHERE (? IS NULL OR source_id=?) ORDER BY source_id,name", (source_id, source_id))

    def history(self, source_id, start_us, end_us, limit=2000):
        limit = min(max(int(limit), 1), 4000)
        return self.query("""SELECT mw.*,ss.session_order,ss.clock_warning
            FROM metric_windows mw JOIN sessions ss USING(session_id)
            WHERE source_id=? AND end_utc_us>? AND start_utc_us<?
            ORDER BY ss.session_order DESC,sequence DESC,metric_id LIMIT ?""",
            (source_id, start_us, end_us, limit + 1))

    def windows(self, start_us, end_us, limit=500):
        return self.query("""SELECT w.*,s.session_order,s.clock_warning,
            (SELECT count(*) FROM aggregates a WHERE a.window_id=w.window_id) AS metric_count
            FROM windows w JOIN sessions s USING(session_id)
            WHERE w.end_utc_us>? AND w.start_utc_us<?
            ORDER BY s.session_order DESC,w.sequence DESC LIMIT ?""", (start_us, end_us, min(int(limit), 500) + 1))

    def window(self, window_id):
        return self.query("""SELECT mw.*,s.display_name,s.source_key FROM metric_windows mw
            JOIN sources s USING(source_id) WHERE window_id=? ORDER BY s.source_id,mw.name""", (window_id,))

    def window_meta(self, window_id):
        rows = self.query("SELECT w.*,s.session_order,s.clock_warning FROM windows w JOIN sessions s USING(session_id) WHERE window_id=?", (window_id,))
        return rows[0] if rows else None

    def alerts(self, source_id=None):
        return self.query("""SELECT e.*,r.label,r.field,r.operator,r.threshold,r.severity,
            m.name,m.unit,m.source_id,s.display_name FROM alert_events e
            JOIN alert_rules r USING(rule_id) JOIN metrics m USING(metric_id)
            JOIN sources s USING(source_id) WHERE (? IS NULL OR m.source_id=?)
            ORDER BY e.last_session_order DESC,e.last_evaluated_utc_us DESC LIMIT 100""", (source_id, source_id))

    def rules(self):
        return self.query("""SELECT r.*,m.name,s.display_name FROM alert_rules r
            JOIN metrics m USING(metric_id) JOIN sources s USING(source_id)
            WHERE enabled=1 ORDER BY created_utc_us DESC LIMIT 256""")

    def counts(self):
        return self.query("""SELECT (SELECT count(*) FROM metrics) AS series,
            (SELECT count(*) FROM windows) AS windows,
            (SELECT count(*) FROM alert_events WHERE closed_utc_us IS NULL) AS open_alerts""")[0]


def metric_value(row):
    return row["sample_sum"] if row["metric_kind"] == "counter" else row["sample_mean"] if row["metric_kind"] == "timer" else row["last_value"]
