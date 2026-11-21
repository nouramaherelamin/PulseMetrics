"""Build and run functional acceptance; save logs outside the source repository."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", choices=["Debug", "Release"], default="Release")
    args = parser.parse_args()
    build = ROOT.parent / "PulseMetrics_V2_BUILD" / args.configuration.lower()
    evidence = ROOT.parent / "PulseMetrics_V2_BUILD/evidence" / datetime.now(timezone.utc).strftime("verification-%Y%m%dT%H%M%SZ")
    evidence.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PULSE_BIN=str(build / "bin"), PYTHONDONTWRITEBYTECODE="1")
    report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(), "python": platform.python_version(),
              "configuration": args.configuration, "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
              "packages": {name: importlib.metadata.version(name) for name in ("streamlit", "plotly", "pandas", "pytest")}, "steps": []}
    commands = [[sys.executable, "scripts/build.py", "--configuration", args.configuration],
                [sys.executable, "-m", "pytest", "tests", "-v", "-p", "no:cacheprovider", "--basetemp", str(evidence / "test-data")]]
    for index, command in enumerate(commands):
        start = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        (evidence / f"step-{index + 1}.log").write_text(result.stdout, encoding="utf-8")
        print(result.stdout, flush=True)
        report["steps"].append({"command": ["python", *command[1:]], "exit_code": result.returncode, "seconds": round(time.monotonic() - start, 3)})
        if result.returncode:
            break
    report["passed"] = len(report["steps"]) == len(commands) and all(s["exit_code"] == 0 for s in report["steps"])
    report["binaries"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((build / "bin").glob("*.exe"))}
    paths = [p for folder in ("native", "python", "database", "config", ".streamlit") for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths.append(ROOT / "CMakeLists.txt")
    report["source_sha256"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    (evidence / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Evidence: {evidence}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
