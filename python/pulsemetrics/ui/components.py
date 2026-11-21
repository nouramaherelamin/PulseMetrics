from datetime import datetime, timezone
from functools import wraps
import html
import os
import shutil
import sqlite3
import time

import plotly.graph_objects as go
import streamlit as st

from pulsemetrics import ipc
from pulsemetrics.data import Data
from .theme import BLUE, CYAN, GRID, ORANGE, TEAL, ico  # noqa: F401  (BLUE/ORANGE/ico re-exported to pages)

SERIES_COLORS = (CYAN, BLUE, TEAL, "#A5B4FC")  # one color per session; sessions are never joined
FILL = {CYAN: "rgba(34,211,238,.13)", BLUE: "rgba(59,130,246,.13)", TEAL: "rgba(45,224,196,.13)", "#A5B4FC": "rgba(165,180,252,.12)"}
PENDING_SLOTS = 6  # native collector bound (docs/architecture.md)


def guarded(function):
    @wraps(function)
    def show(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (sqlite3.Error, RuntimeError, OSError, TimeoutError, ValueError) as exc:
            st.error(f"This control is unavailable: {exc}")
            st.caption("No successful change is implied. Check application health and retry.")
    return show


def database():
    path = os.environ.get("PULSE_DATABASE")
    if not path:
        raise RuntimeError("Start the application with scripts/launch.py")
    return Data(path)


def utc(microseconds):
    return datetime.fromtimestamp(microseconds / 1e6, timezone.utc) if microseconds else None


def timestamp(microseconds):
    return utc(microseconds).strftime("%d %b %Y · %H:%M:%S UTC") if microseconds else "Not yet observed"


def clock(microseconds):
    return utc(microseconds).strftime("%H:%M:%S UTC") if microseconds else "not yet observed"


def title(eyebrow, heading, description):
    """Page heading. Returns a container that status() fills with live state pills."""
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    with left:
        st.html(f'<div class="pm-eyebrow">{html.escape(eyebrow)}</div>')
        st.title(heading)
        st.caption(description)
    return right.container()


def system_drive():
    """Live usage of the system drive from the operating system, or None. Read on demand; never stored."""
    drive = os.environ.get("SystemDrive") or "C:"
    root, label = (drive + "\\", drive) if os.name == "nt" else (os.sep, os.sep)
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return None
    return {"label": label, "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.used / usage.total * 100 if usage.total else None}


def panel(icon_name, heading, hint=""):
    """Panel header: optional bundled icon, heading, small muted hint."""
    glyph = ico(icon_name, 30) if icon_name else ""
    small = f"<small>{html.escape(hint)}</small>" if hint else ""
    return f'<div class="pm-panel-h">{glyph}<h4>{html.escape(heading)}</h4>{small}</div>'


def pill(level, text, tip=""):
    dot = '<i class="dot"></i>'
    return f'<span class="pm-pill {level}" title="{html.escape(tip)}">{dot}{html.escape(text)}</span>'


def state_pills(state, stale):
    """Header pills built only from the controller status reply."""
    live, health = state["live"], state["collector"]
    running = health.get("state") == "running"
    pills = [pill("ok" if running else "bad", "Collector running" if running else "Collector unavailable")]
    sampled = live.get("sampled_at_us")
    pills.append(pill("warn" if stale else "", "Live sample · " + (clock(sampled) if sampled else "none yet"), timestamp(sampled)))
    commit = health.get("last_commit_us")
    pills.append(pill("", "Last commit · " + clock(commit), timestamp(commit)))
    return '<div class="pm-pills">' + "".join(pills) + "</div>"


def status(header=None):
    state = ipc.request("status")
    if state["state"] != "running":
        if state["state"] == "stopped":
            result = state.get("exit_result") or {}
            if result.get("clean"):
                st.success("PulseMetrics has stopped. Your committed history is preserved. You can close this tab.")
            else:
                st.error("Shutdown completed with uncommitted data or component errors. Inspect last_shutdown.json before restarting.")
                st.json(result)
            ipc.request("exit_result_seen")
        else:
            st.info("Stopping monitoring and committing the final window…")
        st.stop()
    live = state["live"]
    stale = live.get("age_seconds") is None or live["age_seconds"] > max(15, state["settings"]["sample_seconds"] * 3)
    if header is not None:
        with header:
            st.html(state_pills(state, stale))
    if stale:
        st.warning("Live measurements are unavailable or stale. Historical records below remain real stored observations.")
    if state.get("monitor_error"):
        st.warning(state["monitor_error"])
    health = state["collector"]
    if health.get("clock_warning"):
        st.warning("The system clock changed. Sessions retain their original timestamps; compare within one session. Retention is paused for this session.")
    if health.get("write_healthy") is False or health.get("state") == "unavailable":
        st.error("Collector persistence is unavailable: " + health.get("last_error", "unknown failure"))
    return state, stale


def health_items(state, stale, counts=None, critical=False):
    """(level, text) checks derived only from reported collector/monitor state."""
    health, live = state.get("collector") or {}, state.get("live") or {}
    items = [("ok", "Collector is running") if health.get("state") == "running" else ("bad", "Collector is unavailable")]
    write = health.get("write_healthy")
    if write is True:
        items.append(("ok", "Database writes are healthy"))
    elif write is False:
        items.append(("bad", "Database writes are failing: " + str(health.get("last_error") or "unknown error")))
    else:
        items.append(("info", "Database write state is not reported"))
    age = live.get("age_seconds")
    if age is None:
        items.append(("warn", "No live sample has been received yet"))
    elif stale:
        items.append(("warn", f"Live sample is stale ({age:.0f} s old)"))
    else:
        items.append(("ok", f"Live sampling is current ({age:.0f} s old)"))
    if state.get("monitor_error"):
        items.append(("warn", str(state["monitor_error"])))
    if health.get("clock_warning"):
        items.append(("warn", "System clock changed; retention is paused for this session"))
    if health.get("backpressure"):
        items.append(("bad", "Write queue is full; newly received lines are refused"))
    elif "pending_batches" in health:
        items.append(("ok", f"Write queue {health['pending_batches']}/{PENDING_SLOTS} batches"))
    if health.get("rejected"):
        items.append(("info", f"{health['rejected']:,} received lines rejected by validation"))
    if counts is not None:
        open_alerts = counts["open_alerts"]
        if open_alerts:
            items.append(("bad" if critical else "warn", f"{open_alerts} open alert{'s' if open_alerts != 1 else ''}"))
        else:
            items.append(("ok", "No open alerts"))
    return items


def health_html(items):
    marks = {"ok": "✓", "warn": "!", "bad": "×", "info": "i"}
    rows = "".join(f'<li class="{level}"><b>{marks[level]}</b><span>{html.escape(text)}</span></li>' for level, text in items)
    return f'<ul class="pm-health">{rows}</ul>'


def ring(percent, label):
    p = max(0.0, min(100.0, percent))
    return f'<div class="pm-ring" style="--p:{p:.2f}" role="img" aria-label="{html.escape(label)}"><span>{p:.0f}%</span></div>'


def bar_row(percent):
    p = max(0.0, min(100.0, percent))
    return f'<div class="pm-barrow">{bar(p)}<em>{p:.0f}%</em></div>'


def bar(percent):
    p = max(0.0, min(100.0, percent))
    return f'<div class="pm-bar" style="--p:{p:.2f}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{p:.1f}"><i></i></div>'


def chips(pairs):
    return '<div class="pm-chips">' + "".join(f'<span class="pm-chip">{html.escape(k)}<b>{html.escape(str(v))}</b></span>' for k, v in pairs) + "</div>"


def value(number, unit="", precision=1):
    return "Unavailable" if number is None else f"{number:,.{precision}f}{unit}"


def chart(rows, name, label, unit, scale=1, field="last_value", key=None, height=270):
    selected = [row for row in rows if row["name"] == name]
    if not selected:
        st.info(f"No stored {label.lower()} observations in this range.")
        return None
    figure = go.Figure()
    sessions = sorted({row["session_order"] for row in selected})
    for index, session in enumerate(sessions):
        ordered = sorted((r for r in selected if r["session_order"] == session), key=lambda r: r["sequence"])
        x, y, custom = [], [], []
        previous = None
        for row in ordered:
            if previous and (row["sequence"] != previous["sequence"] + 1 or row["start_utc_us"] - previous["end_utc_us"] > 100000):
                x.append(utc(row["start_utc_us"])); y.append(None); custom.append(None)
            x.append(utc(row["end_utc_us"])); y.append(row[field] / scale); custom.append(row["window_id"])
            previous = row
        color = SERIES_COLORS[index % len(SERIES_COLORS)]
        # Straight segments, breaks at missing windows (None + connectgaps=False): no smoothing, no interpolation.
        figure.add_trace(go.Scatter(x=x, y=y, customdata=custom, mode="lines+markers", connectgaps=False, line_shape="linear",
                                   fill="tozeroy", fillcolor=FILL[color], name=f"Session {session}",
                                   line=dict(color=color, width=2), marker=dict(size=3, color=color),
                                   hovertemplate=f"%{{x|%d %b %H:%M:%S UTC}}<br>%{{y:.2f}} {unit}<br>Window %{{customdata}}<extra></extra>"))
    figure.update_layout(height=height, margin=dict(l=8, r=12, t=28 if len(sessions) > 1 else 12, b=8), paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#C9D6EE", family="Segoe UI, sans-serif"),
                         showlegend=len(sessions) > 1, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                         xaxis=dict(title="Window end · UTC", gridcolor=GRID, zeroline=False),
                         yaxis=dict(title=unit, gridcolor=GRID, rangemode="tozero", zeroline=False),
                         hovermode="x unified", uirevision=key or name)
    return st.plotly_chart(figure, key=key, config={"displaylogo": False}, on_select="rerun", selection_mode="points")


ALERT_DOT = {"recovered": "green", "rule_disabled": "orange", "source_ended": "gray"}


def alert_list(rows, maximum=4, navigate_key=None):
    if not rows:
        st.caption("No threshold events recorded. Add a rule from Alerts to evaluate future collected windows.")
    for row in rows[:maximum]:
        if row["closed_utc_us"] is None:
            state, dot = "Open · awaiting recovery", "red" if row.get("severity") == "critical" else "orange"
        else:
            state, dot = "Closed · " + row["close_reason"].replace("_", " "), ALERT_DOT.get(row["close_reason"], "gray")
        st.markdown(f":{dot}[●] **{html.escape(row['label'])}**")
        st.caption(f"{state} · {row['display_name']} · {row['name']} · {row['last_value']:.2f} {row['unit']} · {timestamp(row['last_evaluated_utc_us'])}")
        if row["last_window_id"] is None:
            st.caption("The supporting window has expired under retention. Event values and timestamps are preserved.")
        elif navigate_key and "history_page" in st.session_state and st.button("Inspect supporting window", key=f"{navigate_key}_{row['event_id']}"):
            st.session_state["history_target"] = row["last_window_id"]
            st.switch_page(st.session_state["history_page"])


def recent_range(seconds=3600):
    end = int(time.time() * 1e6)
    return end - seconds * 1000000, end
