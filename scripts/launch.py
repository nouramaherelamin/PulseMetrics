"""One-command local launch; never installs packages or modifies system PATH."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from pulsemetrics.controller import Controller


def main():
    parser = argparse.ArgumentParser(description="PulseMetrics V2")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "PulseMetricsV2")
    parser.add_argument("--bin-dir", type=Path, default=ROOT.parent / "PulseMetrics_V2_BUILD/debug/bin")
    parser.add_argument("--no-browser", action="store_true", help="Start the server without opening a browser")
    args = parser.parse_args()
    controller = None
    try:
        controller = Controller(args.data_dir, args.bin_dir)
        controller.native_start()
        url = controller.ui_start(open_browser=not args.no_browser)
        print(f"PulseMetrics is ready: {url}\nData: {controller.directory}", flush=True)
        controller.serve()
    except KeyboardInterrupt:
        pass  # finally performs the same checked native shutdown as the UI
    except Exception as exc:
        print(f"PulseMetrics could not start: {exc}", file=sys.stderr)
        return 1
    finally:
        if controller:
            controller.close()
    return 0 if controller and controller.exit_result and controller.exit_result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
