#!/usr/bin/env python3
"""Render the project-page banner to docs/banner.png, 1600 by 400.

The two recipe strips are read out of results/labelsweep_dataset.jsonl rather than
written into the page, so the banner always shows the recipes the sweep actually
found. Fonts are inlined as data URIs, because a page opened from a file cannot
load them by path. Needs a headless Chromium: pass its path as the first argument,
or set CHROME.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
SWEEP = DOCS.parent / "results" / "labelsweep_dataset.jsonl"
DESIGN = "gcd"

# each ABC transform gets a colour; the -z variants share their parent's colour, faded
FAMILIES = ("balance", "rewrite", "refactor", "resub")


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def strip(steps):
    """One block per transform, coloured by family and faded for the -z variants."""
    out = []
    for step in steps:
        family = step.split()[0]
        if family not in FAMILIES:
            raise SystemExit(f"unknown transform in recipe: {step}")
        faded = " z" if step.endswith("-z") else ""
        out.append(f'<i class="{family}{faded}"></i>')
    return "".join(out)


def recipes():
    """resyn2 and the smallest recipe that still meets the design's timing."""
    rows = [json.loads(line) for line in SWEEP.read_text().splitlines() if line.strip()]
    kept = [r for r in rows if r["design"] == DESIGN and r["ok"] and r["meets_timing"]]
    if not kept:
        raise SystemExit(f"no clean {DESIGN} runs in {SWEEP}")
    base = next(r for r in kept if r["is_resyn2"])
    best = min(kept, key=lambda r: r["area"])
    return base, best


def main():
    chrome = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CHROME")
    if not chrome:
        sys.exit("usage: render.py <path to headless chromium>  (or set CHROME)")

    base, best = recipes()
    delta = (best["area"] - base["area"]) / base["area"] * 100
    slots = {
        "INTER": data_uri(HERE / "fonts/inter-var-latin.woff2", "font/woff2"),
        "SERIF": data_uri(HERE / "fonts/source-serif-4-var-latin.woff2", "font/woff2"),
        "RESYN2_STRIP": strip(base["steps"]),
        "BEST_STRIP": strip(best["steps"]),
        "RESYN2_N": str(len(base["steps"])),
        "BEST_N": str(len(best["steps"])),
        "RESYN2_AREA": f"{base['area']:.1f} µm²",
        "BEST_AREA": f"{best['area']:.1f} µm²",
        "DELTA": f"−{abs(delta):.1f}%",
    }

    page = (HERE / "banner.html").read_text()
    for key, value in slots.items():
        page = page.replace("{{" + key + "}}", value)

    out = DOCS / "banner.png"
    with tempfile.TemporaryDirectory() as tmp:
        filled = Path(tmp) / "banner.html"
        filled.write_text(page)
        subprocess.run([chrome, "--headless", "--no-sandbox", "--hide-scrollbars",
                        "--window-size=1600,400", "--force-device-scale-factor=1",
                        "--virtual-time-budget=3000", f"--screenshot={out}",
                        filled.as_uri()], check=True, capture_output=True)
    print(f"{out}  ({len(base['steps'])} vs {len(best['steps'])} steps, {delta:+.2f}%)")


if __name__ == "__main__":
    main()
