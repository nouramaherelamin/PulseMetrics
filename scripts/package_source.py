"""Create a new source-only Git archive without touching runtime data."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import uuid

root = Path(__file__).resolve().parents[1]
if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
    raise SystemExit("Commit the reviewed source before packaging; working tree is not clean.")
revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True).strip()
destination = root.parent / "PulseMetrics_V2_RELEASES"
destination.mkdir(exist_ok=True)
archive = destination / f"PulseMetrics-V2-{revision}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}.zip"
subprocess.run(["git", "archive", "--format=zip", "--prefix=PulseMetrics_V2/", "--output", str(archive), "HEAD"], cwd=root, check=True)
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
print(archive)
print("SHA256:", checksum)
