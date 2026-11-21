import os
import sqlite3
import uuid

import streamlit as st

from pulsemetrics import ipc
from pulsemetrics.ui.components import database, guarded, health_html, health_items
from pulsemetrics.ui import pages, theme

st.set_page_config(page_title="PulseMetrics", page_icon=":material/monitoring:", layout="wide")
theme.inject()
with st.sidebar:
    st.html('<div class="pm-brand"><b>Pulse<span>Metrics</span></b></div>'
            '<div class="pm-tagline">Local PC performance intelligence</div>')


@st.dialog("Settings")
@guarded
def settings():
    current = ipc.request("status")
    with st.form("settings_form"):
        fields = {}
        for key, label, high in [("sample_seconds", "Sampling interval · seconds", 60), ("window_seconds", "Aggregation window · seconds", 60), ("refresh_seconds", "Dashboard refresh · seconds", 60), ("retention_days", "History retention · days", 30)]:
            fields[key] = st.number_input(label, min_value=1, max_value=high, value=current["settings"][key], step=1)
        st.caption("Collection and retention changes apply on the next launch. Refresh changes apply immediately.")
        if st.form_submit_button("Save settings", type="primary"):
            try:
                ipc.request("save_settings", fields)
                st.session_state["refresh"] = fields["refresh_seconds"]
                st.rerun()
            except (RuntimeError, OSError, TimeoutError) as exc:
                st.error(str(exc))


@st.dialog("Collector & database health", width="large")
@guarded
def health():
    current = ipc.request("status")
    st.caption("Accepted observations are in memory until a successful database commit. UDP loss before receipt cannot be measured.")
    counts = database().counts()
    live = current["live"]
    stale = live.get("age_seconds") is None or live["age_seconds"] > max(15, current["settings"]["sample_seconds"] * 3)
    st.html(health_html(health_items(current, stale, counts)))
    st.json(current["collector"])
    st.write("Stored catalog and history", counts)
    if current["restart_required"]:
        st.info("Saved collection settings will apply after restart.")


@st.dialog("Alerts", width="large")
@guarded
def alerts():
    from pulsemetrics.ui.components import alert_list
    db = database()
    st.caption("Rules evaluate actual committed windows. Missing observations leave an event unresolved; they do not mean recovery.")
    alert_list(db.alerts(), 10, navigate_key="alert_panel")
    with st.expander("Create a threshold rule"):
        metrics = db.metrics()
        if metrics:
            metric = st.selectbox("Metric", metrics, format_func=lambda m: f"{m['display_name']} · {m['name']} [{m['unit']}]")
            fields = ["sum", "rate"] if metric["kind"] == "counter" else ["mean", "min", "max"] if metric["kind"] == "timer" else ["last", "mean", "min", "max"]
            with st.form("alert_rule"):
                label = st.text_input("Rule name", max_chars=120)
                left, right = st.columns(2)
                field = left.selectbox("Evaluate", fields)
                operator = right.selectbox("Condition", ["gt", "ge", "lt", "le"], format_func=lambda k: {"gt": "Greater than", "ge": "At least", "lt": "Less than", "le": "At most"}[k])
                threshold = st.number_input("Threshold · metric units (rate uses count/s)", value=80.0, min_value=-1e12, max_value=1e12)
                severity = st.selectbox("Severity", ["warning", "critical"])
                if st.form_submit_button("Create rule", type="primary"):
                    try:
                        if not label.strip():
                            raise ValueError("Enter a rule name")
                        request_id = st.session_state.setdefault("rule_request_id", str(uuid.uuid4()))
                        ipc.request("add_rule", {"metric_id": metric["metric_id"], "label": label.strip(), "field": field, "operator": operator, "threshold": threshold, "severity": severity}, request_id=request_id)
                        st.session_state.pop("rule_request_id", None)
                        st.success("Rule created. Future committed observations will be evaluated.")
                    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                        st.error(str(exc))
    rules = db.rules()
    if rules:
        st.divider()
        rule = st.selectbox("Active rule", rules, format_func=lambda r: f"{r['label']} · {r['display_name']} / {r['name']}")
        if st.button("Disable selected rule"):
            try:
                ipc.request("disable_rule", {"rule_id": rule["rule_id"]})
                st.rerun()
            except (RuntimeError, OSError, TimeoutError) as exc:
                st.error(str(exc))


@st.dialog("Exit PulseMetrics")
@guarded
def exit_dialog():
    st.write("Stop native monitoring, commit the final window, and close the local application server.")
    st.caption("Closing a browser tab alone leaves collection running.")
    if st.button("Exit PulseMetrics", type="primary"):
        ipc.request("exit")
        st.rerun()


refresh = st.session_state.get("refresh", int(os.environ.get("PULSE_REFRESH", "5")))


def render(function):
    @st.fragment(run_every=refresh)
    def content():
        try:
            function()
        except (sqlite3.Error, RuntimeError, OSError, TimeoutError, ValueError) as exc:
            st.error(f"This view is unavailable: {exc}")
            st.caption("No substitute measurements are shown. Retry after checking collector health or restart the launcher.")
    content()


overview = st.Page(lambda: render(pages.overview), title="Overview", default=True, url_path="overview")
explorer = st.Page(lambda: render(pages.explorer), title="Process Explorer", url_path="processes")
analytics = st.Page(lambda: render(pages.analytics), title="Performance Analytics", url_path="analytics")
history = st.Page(lambda: render(pages.time_machine), title="Performance Time Machine", url_path="history")
st.session_state["analytics_page"] = analytics
st.session_state["history_page"] = history
navigation = st.navigation([overview, explorer, analytics, history], position="hidden")
try:
    open_alerts = database().counts()["open_alerts"]
except (RuntimeError, OSError, sqlite3.Error):
    open_alerts = 0  # no badge when history is unreadable; the pages report the error
with st.sidebar:
    for key, page in (("nav_overview", overview), ("nav_explorer", explorer), ("nav_analytics", analytics), ("nav_history", history)):
        active = navigation.title == page.title
        with st.container(key="navon" if active else f"navoff_{key}"):
            with st.container(key=key):
                st.page_link(page, label=page.title)
    st.html('<div class="pm-section">MONITORING &amp; CONTROL</div>')
    with st.container(key="ctl_alerts_wrap"):
        if st.button("Alerts", key="ctl_alerts", width="stretch"):
            alerts()
        if open_alerts:
            st.html(f'<span class="pm-badge" title="{open_alerts} open alert{"s" if open_alerts != 1 else ""}">{open_alerts}</span>')
    if st.button("Settings", key="ctl_settings", width="stretch"):
        settings()
    if st.button("Collector Health", key="ctl_health", width="stretch"):
        health()
    if st.button("Exit PulseMetrics", key="ctl_exit", width="stretch"):
        exit_dialog()
navigation.run()
