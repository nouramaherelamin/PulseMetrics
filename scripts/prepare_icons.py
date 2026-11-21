"""Developer tool: turn the supplied neon PNG artwork into small WebP UI icons.

Usage: python scripts/prepare_icons.py <source_dir>
Each source file is matched by the 8-character id prefix below, cropped to its visible
(alpha) bounds, centred on a square transparent canvas and resized. Output is committed
to python/pulsemetrics/ui/assets/icons/ so the application needs no network or Pillow.
"""
from pathlib import Path
import sys

from PIL import Image

NAV = 72      # sidebar navigation icons
LARGE = 128   # cards, header and panel icons
ICONS = {
    "a056c167": ("alerts_bell_panel", LARGE), "9ce876ac": ("computer_monitor", LARGE),
    "d0c2103b": ("cpu_chip_metric", LARGE), "564cf815": ("cpu_chip_top", LARGE),
    "b2df5a0c": ("disk_metric", LARGE), "fc9035ff": ("disk_top", LARGE),
    "8305a712": ("health_heart", LARGE), "dbefa778": ("nav_alerts_bell", NAV),
    "4bd90b56": ("nav_collector_health", NAV), "b688881e": ("nav_exit_power", NAV),
    "94db3a9c": ("nav_overview_home", NAV), "1d7fc48e": ("nav_performance_analytics", NAV),
    "c541204d": ("nav_process_explorer", NAV), "eb361320": ("nav_settings_gear", NAV),
    "66a9f1bd": ("nav_time_machine", NAV), "33a75d3d": ("network_metric", LARGE),
    "a2cbf9be": ("ram_metric", LARGE), "5d0125f6": ("ram_top", LARGE),
    "6a9b24e5": ("time_machine_clock", LARGE), "4e767f8a": ("process_stack", LARGE),
}


def convert(source, target, size):
    image = Image.open(source).convert("RGBA")
    box = image.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
    image = image.crop(box)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    inner = round(size * 0.9)  # keep a little glow margin
    canvas = canvas.resize((inner, inner), Image.LANCZOS)
    final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final.paste(canvas, ((size - inner) // 2, (size - inner) // 2))
    final.save(target, "WEBP", quality=88, method=6)


def main():
    source = Path(sys.argv[1])
    target = Path(__file__).resolve().parent.parent / "python/pulsemetrics/ui/assets/icons"
    target.mkdir(parents=True, exist_ok=True)
    for prefix, (name, size) in ICONS.items():
        match = next(source.glob(f"{prefix}*.png"))
        convert(match, target / f"{name}.webp", size)
    print(sum(p.stat().st_size for p in target.glob("*.webp")), "bytes in", len(ICONS), "icons")


if __name__ == "__main__":
    main()
