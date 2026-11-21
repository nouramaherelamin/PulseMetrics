"""Render the redesigned pages with Streamlit AppTest against a synthetic fixture (no native processes needed).

The controller reply is replaced by a fixed status dict; stored history comes from a real SQLite file built
from database/schema.sql. This checks that every page still renders and that the contracts other tests rely on
(titles, button labels, metric/chart counts) hold. It does not test pixel layout or real browser behavior.
"""
import pytest
from streamlit.testing.v1 import AppTest

from pulsemetrics import ipc
from pulsemetrics.controller import ROOT
from ui_fixture import make_db, status_state


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("PULSE_DATABASE", make_db(str(tmp_path / "fixture.sqlite")))
    state = status_state()
    process = dict(name="msedge.exe", pid=5960, created="134394092391888196", source="p.5960.134394092391888196",
                   cpu_percent=1.8, memory_bytes=359.8 * 2**20, state="accessible", tracked=False)
    monkeypatch.setattr(ipc, "request", lambda op, args=None, **kw: state if op == "status" else {"total": 1, "rows": [process]})
    return state


def page(name):
    return AppTest.from_string(f"import streamlit as st\nfrom pulsemetrics.ui.pages import {name}\nst.set_page_config(layout='wide')\n{name}()", default_timeout=20).run()


def test_full_app_overview_and_sidebar(fixture):
    app = AppTest.from_file(str(ROOT / "python/pulsemetrics/ui/app.py"), default_timeout=20).run()
    assert not app.exception, app.exception
    assert app.title[0].value == "Overview"
    assert [m.label for m in app.metric][:2] == ["CPU Usage", "Memory in use"] and len(app.metric) == 4
    assert app.metric[3].label == "Network" and app.metric[3].value == "Not collected"
    labels = {b.label for b in app.button}
    assert {"Alerts", "Settings", "Collector Health", "Exit PulseMetrics", "Open Time Machine"} <= labels
    next(b for b in app.button if b.label == "Alerts").click().run()
    assert not app.exception, app.exception
    assert any("CPU Alert Test" in m.value for m in app.markdown)
    next(b for b in app.button if b.label == "Collector Health").click().run()
    assert not app.exception, app.exception


def test_explorer_analytics_time_machine_render(fixture):
    explorer = page("explorer")
    assert not explorer.exception, explorer.exception
    assert explorer.title[0].value == "Process Explorer"
    assert any(b.label == "Track process" for b in explorer.button)
    analytics = page("analytics")
    assert not analytics.exception, analytics.exception
    assert len(analytics.get("plotly_chart")) == 5  # system source: five stored metric series
    history = page("time_machine")
    assert not history.exception, history.exception
    assert history.selectbox[0].label == "Stored window" and len(history.dataframe) >= 1


def test_unavailable_live_values_are_not_zero(fixture):
    fixture["live"]["age_seconds"] = None
    fixture["live"]["system"] = {}
    app = AppTest.from_file(str(ROOT / "python/pulsemetrics/ui/app.py"), default_timeout=20).run()
    assert not app.exception, app.exception
    assert [m.value for m in app.metric][:2] == ["Unavailable", "Unavailable"] and "0.0%" not in [m.value for m in app.metric]
