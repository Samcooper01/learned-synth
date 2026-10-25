#!/usr/bin/env python3
"""Render the project-page banner to docs/banner.png, 1600 by 400.

The bar chart is the headline per-design result, drawn in the banner's own palette so
its numbers cannot disagree with the headline beside it. Fonts are inlined as data URIs, because a page opened from a file cannot
load them by path. Needs a headless Chromium: pass its path as the first argument,
or set CHROME.
"""
import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
# The headline table, as the repository README publishes it: for each design, the best
# recipe found by any search that still meets the design's clock, against resyn2 on the
# finished layout. gcd through mock-cpu come from the random sweep (results/HEADLINE.md);
# riscv32i's win is the directed search's alone (results/FLAGSHIP.md), which is why the
# two write-ups count 5 wins and 6 wins respectively.
RESULTS = [
    ("gcd", 5.77),
    ("jpeg", 2.19),
    ("ethmac", 2.09),
    ("riscv32i", 0.81),
    ("mock-alu", 0.70),
    ("mock-cpu", 0.22),
    ("aes", None),
    ("uart", None),
    ("ibex", None),
]


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def chart():
    """One row per design; the bar is the area saved, scaled to the largest win."""
    top = max(v for _, v in RESULTS if v is not None)
    rows = []
    for name, saved in RESULTS:
        if saved is None:
            rows.append(f'<div class="bar none"><span class="name">{name}</span>'
                        f'<span class="track"></span><span class="val">none</span></div>')
        else:
            rows.append(f'<div class="bar"><span class="name">{name}</span>'
                        f'<span class="track"><i class="fill" style="width:{saved / top * 100:.1f}%"></i></span>'
                        f'<span class="val">\u2212{saved:.1f}%</span></div>')
    return "".join(rows)


def main():
    chrome = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CHROME")
    if not chrome:
        sys.exit("usage: render.py <path to headless chromium>  (or set CHROME)")

    slots = {
        "INTER": data_uri(HERE / "fonts/inter-var-latin.woff2", "font/woff2"),
        "SERIF": data_uri(HERE / "fonts/source-serif-4-var-latin.woff2", "font/woff2"),
        "CHART": chart(),
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
    wins = sum(1 for _, v in RESULTS if v is not None)
    print(f"{out}  ({wins} of {len(RESULTS)} designs beat resyn2)")


if __name__ == "__main__":
    main()
