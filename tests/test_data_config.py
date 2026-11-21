import json
import sqlite3

import pytest

from pulsemetrics.controller import atomic_json, validate_settings
from pulsemetrics.data import Data


def test_read_only_and_explicit_database_errors(tmp_path):
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        Data(missing).sources()
    assert not missing.exists()
    with sqlite3.connect(missing) as db:
        db.execute("CREATE TABLE fixture(value INTEGER)")
        db.execute("INSERT INTO fixture VALUES(9)")
    read = Data(missing)
    assert read.query("SELECT value FROM fixture") == [{"value": 9}]
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        read.query("INSERT INTO fixture VALUES(10)")
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        read.sources()


def test_atomic_configuration_failure_preserves_previous(tmp_path, monkeypatch):
    from pulsemetrics import controller
    path = tmp_path / "config.json"
    atomic_json(path, {"retention_days": 7})
    def fail(*args):
        raise PermissionError("injected replace refusal")
    monkeypatch.setattr(controller.os, "replace", fail)
    with pytest.raises(PermissionError):
        atomic_json(path, {"retention_days": 6})
    assert json.loads(path.read_text()) == {"retention_days": 7}


def test_settings_type_and_window_validation():
    good = dict(sample_seconds=5, window_seconds=10, refresh_seconds=5, retention_days=7, udp_port=8125, ui_port=8501)
    validate_settings(good)
    for change in ({"sample_seconds": True}, {"sample_seconds": 20}, {"retention_days": 0}, {"refresh_seconds": 5.5}):
        with pytest.raises(ValueError):
            validate_settings(dict(good, **change))
