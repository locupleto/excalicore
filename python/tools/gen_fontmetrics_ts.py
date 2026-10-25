"""Write ``typescript/src/fontmetrics.ts`` from ``excalicore.fontmetrics``.

The glyph tables are data, not logic: the Python module holds them, and this
copies them across so the two halves cannot differ by a typo. It also writes
the East-Asian-width ranges (``W`` and ``F``) that ``elements._advance``
reads from ``unicodedata`` — JavaScript has no such property, so the ranges
are taken from the Python being run and listed as data.

Run from ``python/``:  python3 tools/gen_fontmetrics_ts.py
"""

from __future__ import annotations

import pathlib
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from excalicore import fontmetrics as fm  # noqa: E402

OUT = HERE.parents[1] / "typescript" / "src" / "fontmetrics.ts"


def wide_ranges() -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for cp in range(0x110000):
        if unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            if ranges and ranges[-1][1] == cp - 1:
                ranges[-1] = (ranges[-1][0], cp)
            else:
                ranges.append((cp, cp))
    return ranges


def rows(values: list[int], indent: str, per: int = 20) -> str:
    return "\n".join(
        indent + ", ".join(str(v) for v in values[i:i + per]) + ","
        for i in range(0, len(values), per)
    )


def main() -> None:
    parts = [f'''/**
 * Glyph advance widths of Excalidraw's font families, in thousandths of an em.
 *
 * Read from the fonts Excalidraw ships (@excalidraw/excalidraw 0.18.x,
 * `dist/prod/fonts`): ASCII and Latin-1/Latin Extended-A. `measureText` in
 * `elements` sums these so an uppercase or wide label is not under-measured
 * by a flat average glyph width.
 *
 * Generated from `python/excalicore/fontmetrics.py` by
 * `python/tools/gen_fontmetrics_ts.py`; do not edit by hand. The East Asian
 * width ranges are Python's `unicodedata` (Unicode {unicodedata.unidata_version}),
 * because JavaScript has no such property.
 */

/** Codepoints covered, in the order of every table below. */
export const CODEPOINTS: readonly number[] = [
  ...Array.from({{ length: 127 - 32 }}, (_, i) => 32 + i),
  ...Array.from({{ length: 384 - 160 }}, (_, i) => 160 + i),
]

/** Font family id -> [average ASCII advance, advances for `CODEPOINTS`]. */
export const METRICS: Readonly<Record<number, readonly [number, readonly number[]]>> = {{''']
    for fid, (avg, widths) in fm.METRICS.items():
        parts.append(f"  {fid}: [\n    {avg},\n    [\n{rows(list(widths), '      ')}\n    ],\n  ],")
    parts.append('''}

/** Font family id -> glyph -> advance. A glyph with no (or a zero) advance is absent. */
export const ADVANCE: Readonly<Record<number, ReadonlyMap<string, number>>> = Object.fromEntries(
  Object.entries(METRICS).map(([fid, [, widths]]) => [
    fid,
    new Map(CODEPOINTS.flatMap((cp, i) => (widths[i] ? [[String.fromCodePoint(cp), widths[i]] as const] : []))),
  ]),
)
''')
    flat = [v for lo, hi in wide_ranges() for v in (lo, hi)]
    parts.append(f'''/** Inclusive [low, high] codepoint pairs whose East Asian Width is W or F, flattened. */
const WIDE: readonly number[] = [
{rows(flat, "  ", 12)}
]

/** Whether `ch` (one codepoint) has East Asian Width W or F: the glyphs that
 *  take a full em. Python's `unicodedata.east_asian_width(ch) in ("W", "F")`. */
export function isWide(ch: string): boolean {{
  const cp = ch.codePointAt(0)
  if (cp === undefined) return false
  let lo = 0
  let hi = WIDE.length / 2 - 1
  while (lo <= hi) {{
    const mid = (lo + hi) >> 1
    if (cp < WIDE[2 * mid]) hi = mid - 1
    else if (cp > WIDE[2 * mid + 1]) lo = mid + 1
    else return true
  }}
  return false
}}
''')
    OUT.write_text("\n".join(parts))
    print(f"wrote {OUT} ({len(flat) // 2} wide ranges, Unicode {unicodedata.unidata_version})")


if __name__ == "__main__":
    main()
