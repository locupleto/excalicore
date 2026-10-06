"""Draw docs/architecture.svg, the layering picture at the top of the README.

An application above, excalicore's modules in the middle, Excalidraw below,
with an arrow for each module an application can import. Light and dark
colours live in one stylesheet inside the SVG, so the picture follows the
reader's theme on GitHub. Re-run after a release that adds or plans a module.

Usage:  python docs/architecture.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1080, 620
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

STYLE = f"""
.bg {{ fill: #ffffff; }}
.box {{ fill: none; stroke: #1f2328; stroke-width: 1.6; }}
.core {{ fill: none; stroke: #8d4b00; stroke-width: 2; }}
.app {{ fill: none; stroke: #1f2328; stroke-width: 1.6; stroke-dasharray: 7 5; }}
.planned {{ fill: none; stroke: #8d4b00; stroke-width: 1.6; stroke-dasharray: 6 4; }}
.use {{ stroke: #2f7d32; stroke-width: 1.6; fill: none; }}
.down {{ stroke: #1f2328; stroke-width: 1.6; fill: none; }}
.head-use {{ fill: #2f7d32; }}
.head-down {{ fill: #1f2328; }}
text {{ font-family: {FONT}; fill: #1f2328; }}
.title {{ font-size: 19px; font-weight: 600; }}
.brass {{ fill: #8d4b00; }}
.name {{ font-size: 15px; font-weight: 600; font-family: {MONO}; }}
.half {{ font-size: 11px; fill: #656d76; }}
.body {{ font-size: 12px; }}
.note {{ font-size: 13px; fill: #656d76; }}
@media (prefers-color-scheme: dark) {{
  .bg {{ fill: #0d1117; }}
  .box, .app {{ stroke: #d1d7e0; }}
  .core, .planned {{ stroke: #e3a255; }}
  .use {{ stroke: #6fc276; }}
  .head-use {{ fill: #6fc276; }}
  .down {{ stroke: #d1d7e0; }}
  .head-down {{ fill: #d1d7e0; }}
  text {{ fill: #e6edf3; }}
  .brass {{ fill: #e3a255; }}
  .half, .note {{ fill: #9198a1; }}
}}
"""

out: list[str] = []


def fits(line: str, width: float, size: float, factor: float = 0.56) -> None:
    need = len(line) * size * factor
    assert need <= width, f"{line!r} needs {need:.0f}px, has {width:.0f}px"


def rect(x, y, w, h, cls, r=10):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" class="{cls}"/>')


def text(x, y, s, cls, anchor="start", width=None, size=None):
    if width and size:
        fits(s, width, size)
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')


def arrow(x1, y1, x2, y2, cls):
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2 - 7}" class="{cls}"/>')
    out.append(f'<path d="M{x2 - 5},{y2 - 9} L{x2},{y2} L{x2 + 5},{y2 - 9} Z" class="head-{cls}"/>')


# ---------------------------------------------------------------- application
APP_X, APP_Y, APP_W, APP_H = 40, 24, W - 80, 112
rect(APP_X, APP_Y, APP_W, APP_H, "app")
text(W / 2, APP_Y + 32, "Your application", "title", "middle")
for i, line in enumerate([
    "what an element means · the vocabulary document · the shelf artwork",
    "prompts · tables and SQL · UI · the layout engine · the palette",
]):
    text(W / 2, APP_Y + 62 + i * 20, line, "body", "middle", APP_W - 40, 12.5)

# ---------------------------------------------------------------- excalicore
CORE_X, CORE_Y, CORE_W, CORE_H = 40, 216, W - 80, 248
rect(CORE_X, CORE_Y, CORE_W, CORE_H, "core", 12)

MOD_Y, MOD_H, MOD_W = CORE_Y + 20, 160, 128
GAP = (CORE_W - 40 - 7 * MOD_W) / 6
modules = [
    ("scene", "Python", ["canvas ↔ model", "compact()", "extract_patch()", "merge patch,", "all or nothing"]),
    ("stencils", "Python + TS", ["the stencil", "contract", "instantiate()", "validate()", "ghostStack()"]),
    ("geometry", "Python + TS", ["anchors, routes,", "loops, bends,", "dragged arrow", "ends, wrap"]),
    ("vocabulary", "Python + TS", ["the grammar", "contract", "validate()", "check()"]),
    ("fidelity", "Python", ["explode()", "reassemble()", "exact database", "round trip"]),
    ("drawio", "Python", ["Diagram", "to_drawio()", "to_svg()", "editable", ".drawio.svg"]),
    ("contrast", "TS, planned", ["readable ink", "against its", "backgrounds"]),
]
centres = {}
for i, (name, half, body) in enumerate(modules):
    x = CORE_X + 20 + i * (MOD_W + GAP)
    cx = x + MOD_W / 2
    centres[name] = cx
    planned = half.endswith("planned")
    rect(x, MOD_Y, MOD_W, MOD_H, "planned" if planned else "box", 8)
    text(cx, MOD_Y + 24, name, "name brass" if planned else "name", "middle", MOD_W - 12, 15 * 1.1)
    text(cx, MOD_Y + 42, half, "half", "middle", MOD_W - 12, 11)
    for j, line in enumerate(body):
        text(x + 10, MOD_Y + 68 + j * 17, line, "body", "start", MOD_W - 16, 12)

text(W / 2, CORE_Y + CORE_H - 40, "excalicore", "title brass", "middle")
text(W / 2, CORE_Y + CORE_H - 16,
     "pure functions · no I/O · no UI · no layout engine · no palette · no vocabulary of its own",
     "note", "middle", CORE_W - 40, 13)

# ---------------------------------------------------------------- excalidraw
XD_X, XD_Y, XD_W, XD_H = 40, 520, W - 80, 76
rect(XD_X, XD_Y, XD_W, XD_H, "box")
text(W / 2, XD_Y + 30, "@excalidraw/excalidraw", "title", "middle")
text(W / 2, XD_Y + 55,
     "elements and their styling · binding · the canvas component the application embeds",
     "note", "middle", XD_W - 40, 13)

# ---------------------------------------------------------------- arrows
for name, *_ in modules:
    if name == "contrast":
        continue
    arrow(centres[name], APP_Y + APP_H, centres[name], MOD_Y, "use")
arrow(W / 2, CORE_Y + CORE_H, W / 2, XD_Y, "down")

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'role="img" aria-label="An application imports excalicore\'s modules; excalicore works on Excalidraw elements">\n'
    f"<style>{STYLE}</style>\n"
    f'<rect x="0" y="0" width="{W}" height="{H}" class="bg"/>\n'
    + "\n".join(out)
    + "\n</svg>\n"
)
target = Path(__file__).with_name("architecture.svg")
target.write_text(svg)
print(f"wrote {target}")
