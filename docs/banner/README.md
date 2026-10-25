# The project-page banner

`banner.html` is the source for `docs/banner.png`, the 1600 by 400 strip at the top of
the repository README. `render.py` fills in the fonts and the two recipe strips and
screenshots the page with a headless Chromium:

    python3 render.py /path/to/chrome

The chart is the headline per-design result: for each design, the best recipe that still
meets its clock, against `resyn2` on the finished layout. It is drawn in the banner's own
palette rather than dropped in as `docs/results.png`, so its numbers cannot disagree with
the headline beside it. `results/HEADLINE.md` counts five wins because it covers the random
sweep alone; riscv32i's win belongs to the directed search in `results/FLAGSHIP.md`, which
is what makes the total six.

Fonts are [Inter](https://github.com/rsms/inter) and
[Source Serif 4](https://github.com/adobe-fonts/source-serif), both under the SIL Open
Font License.
