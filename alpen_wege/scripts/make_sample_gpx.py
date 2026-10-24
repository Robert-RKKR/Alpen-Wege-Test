#!/usr/bin/env python3
"""Generate sample GPX files for manual testing.

Usage:
    python scripts/make_sample_gpx.py                       # all variants to ./data/gpx/samples/
    python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.gpx_factory import climb, make_gpx, save_gpx, straight_line


VARIANTS = {
    "full": "Full track with timestamps, elevation, HR",
    "no-time": "Track without timestamps",
    "no-ele": "Track without elevation data",
    "two-trk": "Multi-track (2 <trk> elements)",
    "route-only": "Route element, no timestamps",
    "broken": "Intentionally broken GPX (no usable points)",
}


def _build_variant(variant: str):
    if variant == "full":
        pts, times, eles = climb(n=200, gain=100, noise_std=0.5)
        hr = [110 + i % 30 for i in range(200)]
        return make_gpx(pts, times=times, elevations=eles, hr=hr, sport_type="hiking")

    elif variant == "no-time":
        pts, _, eles = straight_line(n=101, step_m=10)
        return make_gpx(pts, elevations=eles, sport_type="hiking")

    elif variant == "no-ele":
        pts, times, _ = straight_line(n=101, step_m=10)
        return make_gpx(pts, times=times, sport_type="hiking")

    elif variant == "two-trk":
        pts, times, eles = straight_line(n=80, step_m=10)
        return make_gpx(pts, times=times, elevations=eles, tracks=2)

    elif variant == "route-only":
        pts, _, eles = straight_line(n=50, step_m=20)
        return make_gpx(pts, elevations=eles, route_only=True)

    elif variant == "broken":
        return '<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1"><trk><trkseg></trkseg></trk></gpx>'

    else:
        raise ValueError(f"Unknown variant: {variant}")


def main():
    parser = argparse.ArgumentParser(description="Generate sample GPX files")
    parser.add_argument(
        "-o", "--out-dir", default="./data/gpx/samples",
        help="Output directory when generating all variants",
    )
    parser.add_argument("--variant", choices=list(VARIANTS.keys()), help="Single variant")
    parser.add_argument("--out", help="Output file path (requires --variant)")
    args = parser.parse_args()

    if args.variant:
        content = _build_variant(args.variant)
        out_path = args.out or f"./{args.variant}.gpx"
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            Path(out_path).write_text(content)
        else:
            save_gpx(content, str(Path(out_path).parent), Path(out_path).name)
        print(f"  {out_path} — {VARIANTS[args.variant]}")
        return

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for variant, desc in VARIANTS.items():
        if variant == "broken":
            Path(out / "broken.gpx").write_text(_build_variant("broken"))
        else:
            gpx = _build_variant(variant)
            save_gpx(gpx, str(out), f"{variant}.gpx")
        print(f"  {variant}.gpx — {desc}")

    print(f"\nAll files written to {out.resolve()}")


if __name__ == "__main__":
    main()
