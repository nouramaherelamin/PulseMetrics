import pytest
from pulsemetrics.analytics import compare_windows, memory_change, summaries


def row(**changes):
    return dict(dict(metric_id=1, name="memory.used", metric_kind="gauge", unit="bytes", sample_count=2,
                     sample_sum=30, sample_max=20, last_value=20, sample_mean=15, elapsed_us=1000000,
                     window_id=1, session_id="first", session_order=1, sequence=0, end_utc_us=2000000,
                     display_name="System", rate=None), **changes)


def test_weighted_summary_and_honest_comparisons():
    samples = [row(), row(sample_count=1, sample_sum=60, sample_max=60, last_value=60, window_id=2, sequence=2)]
    assert summaries(samples)[0]["mean"] == 30  # (10+20+60)/3, not average of averages
    insight = memory_change(samples)
    assert insight["delta_bytes"] == 40 and (insight["first_window"], insight["last_window"]) == (1, 2)
    assert compare_windows([samples[1]], [samples[0]])[0]["Change"] == 40
    assert not compare_windows([row(session_id="second")], [row()])
    assert memory_change([row(), row(session_order=2, sequence=1)]) is None
    counters = [row(metric_kind="counter", unit="count", sample_sum=5, rate=5), row(metric_kind="counter", unit="count", sample_sum=15, elapsed_us=3000000, rate=5)]
    assert summaries(counters)[0]["rate"] == 5
