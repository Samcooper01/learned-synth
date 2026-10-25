# The project-page banner

`banner.html` is the source for `docs/banner.png`, the 1600 by 400 strip at the top of
the repository README. `render.py` fills in the fonts and the two recipe strips and
screenshots the page with a headless Chromium:

    python3 render.py /path/to/chrome

The strips are not written into the page. `render.py` reads
`results/labelsweep_dataset.jsonl`, takes `resyn2` and the smallest recipe that still
meets gcd's timing, and draws one block per transform, coloured by family and faded for
the `-z` variants. Rerun the sweep and the banner follows it.

Fonts are [Inter](https://github.com/rsms/inter) and
[Source Serif 4](https://github.com/adobe-fonts/source-serif), both under the SIL Open
Font License.
