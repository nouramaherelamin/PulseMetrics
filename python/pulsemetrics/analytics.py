"""Small, evidence-based calculations over committed native aggregates."""
from collections import defaultdict


def summaries(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["metric_id"]].append(row)
    result = []
    for metric_id, samples in groups.items():
        first = samples[0]
        count = sum(r["sample_count"] for r in samples)
        total = sum(r["sample_sum"] for r in samples)
        result.append({"metric_id": metric_id, "name": first["name"], "kind": first["metric_kind"], "unit": first["unit"],
                       "observations": count, "windows": len(samples), "mean": total / count,
                       "peak": max(r["sample_max"] for r in samples), "sum": total,
                       "rate": total * 1e6 / sum(r["elapsed_us"] for r in samples) if first["metric_kind"] == "counter" else None})
    return result


def memory_change(rows):
    candidates = [r for r in rows if r["unit"] == "bytes" and r["name"] in ("memory.used", "memory.working_set")]
    if not candidates:
        return None
    session = max(r["session_order"] for r in candidates)
    samples = sorted((r for r in candidates if r["session_order"] == session), key=lambda r: r["sequence"])
    if len(samples) < 2:
        return None
    first, last = samples[0], samples[-1]
    return {"delta_bytes": last["last_value"] - first["last_value"], "first_window": first["window_id"],
            "last_window": last["window_id"], "first_value": first["last_value"], "last_value": last["last_value"],
            "start_us": first["end_utc_us"], "end_us": last["end_utc_us"], "session_order": session}


def compare_windows(current, previous):
    earlier = {r["metric_id"]: r for r in previous}
    comparisons = []
    for row in current:
        before = earlier.get(row["metric_id"])
        if not before or before["session_id"] != row["session_id"] or before["unit"] != row["unit"] or before["metric_kind"] != row["metric_kind"]:
            continue
        field = "rate" if row["metric_kind"] == "counter" else "sample_mean" if row["metric_kind"] == "timer" else "last_value"
        unit = "count/s" if field == "rate" else row["unit"]
        comparisons.append({"Source": row["display_name"], "Metric": row["name"], "Unit": unit,
                            "Previous": before[field], "Selected": row[field], "Change": row[field] - before[field]})
    return comparisons
