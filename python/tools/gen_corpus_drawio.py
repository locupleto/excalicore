"""Generate ``corpus/drawio/cases.json`` by EXECUTING ``excalicore.drawio``.

Run from ``python/`` (no dependencies)::

    python3 tools/gen_corpus_drawio.py

Every expected string in the output is what the Python implementation wrote
for the diagram beside it; nothing is typed by hand. The TypeScript half
(``typescript/tests/drawio.test.ts``) must write the same strings, byte for
byte, and ``TestCorpus`` in ``tests/test_drawio.py`` checks Python still does.
Only the diagrams (the inputs) are authored here, and only neutral ones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from excalicore import drawio  # noqa: E402

OUT = HERE.parent.parent / "corpus" / "drawio" / "cases.json"

DOC = (
    "Cases were executed by calling excalicore.drawio (python/excalicore/drawio.py) via "
    "python/tools/gen_corpus_drawio.py; every expected string is Python's own output. "
    "`diagram` is {name, fontFamily?, cells}; `cells` are replayed in order as "
    "{op: 'container', id, label, box, parent?, style?}, "
    "{op: 'vertex', id, lines, box, shape?, parent?, style?} or "
    "{op: 'edge', id, source, target, points, lines?, labelAt?, style?} calls "
    "(box = [x, y, w, h]; absent options take the function's default). `svgOptions` "
    "({margin?, background?}) is passed to to_svg/toSvg. `expect` is either "
    "{buildError: {type, message}} — the LAST cell's call raised — or "
    "{drawio: R, svg: R, bounds: [x, y, w, h]} where R is {output: <exact text>} "
    "(`.drawio` / `.drawio.svg`, the UTF-8 text) or {error: {type, message}} (the "
    "check that to_drawio/to_svg makes, or a style number that does not parse). "
    "Error type is the Python exception name; TypeScript throws ValueError with the "
    "same message."
)


def container(id, label, box, parent=None, style=None):
    c = {"op": "container", "id": id, "label": label, "box": box}
    if parent is not None:
        c["parent"] = parent
    if style is not None:
        c["style"] = style
    return c


def vertex(id, lines, box, shape=None, parent=None, style=None):
    c = {"op": "vertex", "id": id, "lines": lines, "box": box}
    if shape is not None:
        c["shape"] = shape
    if parent is not None:
        c["parent"] = parent
    if style is not None:
        c["style"] = style
    return c


def edge(id, source, target, points, lines=None, labelAt=None, style=None):
    c = {"op": "edge", "id": id, "source": source, "target": target, "points": points}
    if lines is not None:
        c["lines"] = lines
    if labelAt is not None:
        c["labelAt"] = labelAt
    if style is not None:
        c["style"] = style
    return c


def case(name, cells, diagram_name="Board", font=None, svg=None):
    d = {"name": diagram_name, "cells": cells}
    if font is not None:
        d["fontFamily"] = font
    c = {"name": name, "diagram": d}
    if svg is not None:
        c["svgOptions"] = svg
    return c


def apply(spec_cell, d):
    op = spec_cell["op"]
    if op == "container":
        d.container(spec_cell["id"], spec_cell["label"], tuple(spec_cell["box"]),
                    parent=spec_cell.get("parent"), style=spec_cell.get("style"))
    elif op == "vertex":
        kw = {}
        if "shape" in spec_cell:
            kw["shape"] = spec_cell["shape"]
        d.vertex(spec_cell["id"], spec_cell["lines"], tuple(spec_cell["box"]),
                 parent=spec_cell.get("parent"), style=spec_cell.get("style"), **kw)
    else:
        d.edge(spec_cell["id"], spec_cell["source"], spec_cell["target"],
               spec_cell["points"], spec_cell.get("lines", ()),
               label_at=spec_cell.get("labelAt"), style=spec_cell.get("style"))


def run(c):
    spec = c["diagram"]
    kw = {"font_family": spec["fontFamily"]} if "fontFamily" in spec else {}
    d = drawio.Diagram(spec["name"], **kw)
    for cell in spec["cells"]:
        try:
            apply(cell, d)
        except Exception as e:  # noqa: BLE001
            return {"buildError": {"type": type(e).__name__, "message": str(e)}}
    svg_kw = c.get("svgOptions", {})

    def result(fn):
        try:
            return {"output": fn().decode("utf-8")}
        except Exception as e:  # noqa: BLE001
            return {"error": {"type": type(e).__name__, "message": str(e)}}

    return {
        "drawio": result(d.to_drawio),
        "svg": result(lambda: d.to_svg(**svg_kw)),
        "bounds": list(d.bounds()),
    }


# --- the diagrams -----------------------------------------------------------------

BOARD = [
    container("inner", "Inner", [120, 140, 400, 200], parent="outer",
              style={"rounded": "1", "fillColor": "#eeeeee"}),
    container("outer", "Outer", [100, 100, 700, 400]),
    vertex("a", ["A box", "its tech"], [150, 200, 120, 60], parent="inner"),
    vertex("db", ["Store"], [600, 200, 120, 60], shape="cylinder", parent="outer"),
    vertex("who", ["Someone"], [0, 0, 60, 60], shape="actor"),
    edge("ab", "a", "db", [[270, 230], [400, 230], [400, 220], [600, 220]], ["reads"],
         style={"strokeColor": "#123456"}),
    edge("wa", "who", "a", [[30, 60], [180, 200]]),
]

CASES = [
    case("an empty diagram", [], "Empty"),
    case("an empty diagram with margin and background", [], "Empty",
         svg={"margin": 0, "background": "none"}),
    case("a name cut at 80 code points, with non-ASCII and an astral letter",
         [vertex("a", ["x"], [0, 0, 50, 30])],
         "Åäö & <ö> \"q\" " + "ä" * 60 + "𝔘" * 10 + "tail"),
    case("the board: nested containers, three shapes, a bent and a straight arrow", BOARD,
         "Board & <co>"),
    case("the board with a custom font family", BOARD, "Board", font="Inter"),
    case("the board with a quoted font family", BOARD, "Board", font='"Inter" & <Mono>'),
    case("the board with margin 7.5 and a background", BOARD, "Board",
         svg={"margin": 7.5, "background": "#fafafa"}),
    case("a background with special characters", [vertex("a", ["x"], [0, 0, 50, 30])], "Backdrop",
         svg={"background": 'url("a")&<b>'}),
    case("three containers deep, children listed before their parents", [
        vertex("leaf", ["Leaf"], [330, 330, 100, 40], parent="c3"),
        container("c3", "Third", [320, 320, 200, 120], parent="c2"),
        vertex("mid", ["Mid"], [230, 230, 100, 40], parent="c2"),
        container("c2", "Second", [210, 210, 400, 300], parent="c1"),
        container("c1", "First", [200, 200, 600, 500]),
        container("sibling", "Sibling", [900, 200, 100, 100]),
        vertex("top", ["Top"], [10, 10, 80, 40]),
    ], "Deep"),
    case("an edge declared first is still written last, between containers", [
        edge("e", "c1", "c2", [[300, 150], [300, 250], [500, 250], [500, 350]], ["across"]),
        container("c1", "One", [100, 100, 300, 100]),
        container("c2", "Two", [400, 350, 300, 100]),
    ], "Between"),
    case("an empty container label draws no text", [
        container("c", "", [0, 0, 100, 100]),
        vertex("v", [], [10, 10, 40, 40]),
        vertex("w", [""], [10, 60, 40, 30]),
    ], "Blank"),
    case("every shape with default style", [
        vertex("r", ["Rect"], [10, 10, 120, 60], shape="rect"),
        vertex("c", ["Cylinder"], [150, 10, 120, 80], shape="cylinder"),
        vertex("a", ["Actor"], [290, 10, 60, 80], shape="actor"),
    ], "Shapes"),
    case("a caller style wins over the structural default, and keeps its place", [
        vertex("c", ["C"], [0, 0, 100, 60], shape="cylinder",
               style={"size": "30", "fillColor": "#abcdef", "boundedLbl": "0"}),
        vertex("a", ["A"], [150, 0, 60, 80], shape="actor",
               style={"verticalLabelPosition": "top", "extra": "1"}),
        container("k", "K", [0, 100, 300, 200],
                  style={"container": "0", "spacingLeft": "30", "fontFamily": "Mono"}),
    ], "Override"),
    case("vertex style options: rounded, absolute arc, dashes, opacity, colours", [
        vertex("r1", ["rounded"], [0, 0, 120, 50], style={"rounded": "1"}),
        vertex("r2", ["abs arc 24"], [140, 0, 120, 50],
               style={"rounded": "1", "absoluteArcSize": "1", "arcSize": "24"}),
        vertex("r3", ["abs arc default"], [280, 0, 120, 50],
               style={"rounded": "1", "absoluteArcSize": "1"}),
        vertex("r4", ["arc without rounded"], [420, 0, 120, 50],
               style={"absoluteArcSize": "1", "arcSize": "40"}),
        vertex("d1", ["dashed"], [0, 80, 120, 50], style={"dashed": "1"}),
        vertex("d2", ["dash pattern"], [140, 80, 120, 50],
               style={"dashed": "1", "dashPattern": "1 1"}),
        vertex("d3", ["not dashed"], [280, 80, 120, 50], style={"dashed": "0"}),
        vertex("o1", ["opacity 50"], [0, 160, 120, 50], style={"opacity": "50"}),
        vertex("o2", ["opacity 12.5"], [140, 160, 120, 50], style={"opacity": "12.5"}),
        vertex("o3", ["opacity 33.333"], [280, 160, 120, 50], style={"opacity": "33.333"}),
        vertex("o4", ["opacity 0"], [420, 160, 120, 50], style={"opacity": "0"}),
        vertex("o5", ["opacity 100"], [560, 160, 120, 50], style={"opacity": "100"}),
        vertex("o6", ["opacity padded"], [700, 160, 120, 50], style={"opacity": " 7_5 "}),
        vertex("c1", ["colours"], [0, 240, 120, 50],
               style={"fillColor": "none", "strokeColor": "#ff0000", "strokeWidth": "3",
                      "fontColor": "#00ff00", "fontSize": "16"}),
        vertex("c2", ["font from stroke"], [140, 240, 120, 50],
               style={"strokeColor": "#0000ff", "fontColor": ""}),
        vertex("c3", ["font fallback"], [280, 240, 120, 50],
               style={"strokeColor": "", "fontColor": ""}),
        vertex("f1", ["font size 9.5"], [420, 240, 120, 50], style={"fontSize": "9.5"}),
        vertex("f2", ["font size 1e1"], [560, 240, 120, 50], style={"fontSize": "1e1"}),
    ], "Options"),
    case("container style options and font-size spacing", [
        container("k1", "Rounded", [0, 0, 200, 100], style={"rounded": "1"}),
        container("k2", "Dashed", [220, 0, 200, 100],
                  style={"dashed": "1", "dashPattern": "3 3", "opacity": "80"}),
        container("k3", "Big", [440, 0, 200, 100],
                  style={"fontSize": "20", "fontColor": "#223344", "strokeColor": "#445566",
                         "strokeWidth": "2", "fillColor": "#f0f0f0", "spacingLeft": "5.25"}),
        container("k4", "Abs", [660, 0, 200, 100],
                  style={"rounded": "1", "absoluteArcSize": "1", "arcSize": "30.5"}),
    ], "Containers"),
    case("rounding ties: coordinates on a binary half of a hundredth", [
        vertex("a", ["t"], [0.125, 0.625, 10.375, 20.875]),
        vertex("b", ["t"], [-0.125, -0.375, 33.0625, 1.005]),
        vertex("c", ["t"], [-0.001, 100.5, 0.004, 0.005]),
        vertex("d", ["t"], [123456789.5, 1e-7, 2.675, 1.115]),
        vertex("e", ["t"], [-0.0, 7, 0.1 + 0.2, 1 / 3]),
    ], "Ties"),
    case("arrow end fractions: ties at four digits, clamps and a flat box", [
        vertex("s", ["S"], [0, 0, 32, 32]),
        vertex("t", ["T"], [100, 100, 32, 0]),
        vertex("u", ["U"], [200, 0, 3, 7]),
        edge("e1", "s", "t", [[1, 1], [101, 100]]),
        edge("e2", "s", "t", [[3, 5], [131, 100]]),
        edge("e3", "s", "t", [[-10, 40], [1000, -5]]),
        edge("e4", "s", "u", [[32, 16], [201, 3.5]]),
        edge("e5", "s", "u", [[0.5, 0.2], [202.9999, 6.99999]]),
        edge("e6", "u", "u", [[200, 3], [203, 3], [203, 8], [201, 8]], ["loop"]),
    ], "Fractions"),
    case("arrow kinds: straight, bent, many bends, loop, to a container, labelled", [
        container("zone", "Zone", [0, 0, 500, 300]),
        vertex("a", ["A"], [20, 40, 100, 50], parent="zone"),
        vertex("b", ["B"], [300, 40, 100, 50], parent="zone"),
        vertex("c", ["C"], [300, 200, 100, 50], parent="zone"),
        vertex("out", ["Out"], [600, 120, 100, 50]),
        edge("straight", "a", "b", [[120, 65], [300, 65]]),
        edge("bent", "a", "c", [[70, 90], [70, 225], [300, 225]], ["bent"]),
        edge("zigzag", "b", "c", [[350, 90], [380, 120], [320, 150], [350, 200]]),
        edge("loop", "a", "a", [[120, 50], [150, 20], [90, 20], [90, 40]], ["again"]),
        edge("toZone", "out", "zone", [[600, 145], [500, 145]], ["in"]),
        edge("fromZone", "zone", "out", [[500, 100], [600, 100]], ["out"]),
        edge("reverse", "b", "a", [[300, 80], [120, 80]], ["back"]),
    ], "Arrows"),
    case("edge labels: positions, backgrounds, lines, font size", [
        vertex("a", ["A"], [0, 0, 100, 50]),
        vertex("b", ["B"], [400, 0, 100, 50]),
        edge("e1", "a", "b", [[100, 25], [400, 25]], ["midpoint"]),
        edge("e2", "a", "b", [[100, 30], [400, 30]], ["placed"], labelAt=[250, 12.5]),
        edge("e3", "a", "b", [[100, 35], [400, 35]], ["white ground", "second line"],
             style={"labelBackgroundColor": "#ffffff", "fontSize": "9"}),
        edge("e4", "a", "b", [[100, 40], [400, 40]], ["none ground"],
             style={"labelBackgroundColor": "none", "fontColor": "#aa0000"}),
        edge("e5", "a", "b", [[100, 45], [400, 45]], ["", "x"],
             style={"labelBackgroundColor": "#ffff00"}),
        edge("e6", "a", "b", [[100, 20], [400, 20]], [""],
             style={"labelBackgroundColor": "#ffff00"}),
        edge("e7", "a", "b", [[100, 10], [400, 10]], [], labelAt=[]),
    ], "Labels"),
    case("edge styles: colours share and split markers, dashes, widths, opacity", [
        vertex("a", ["A"], [0, 0, 100, 50]),
        vertex("b", ["B"], [300, 0, 100, 50]),
        edge("e1", "a", "b", [[100, 10], [300, 10]]),
        edge("e2", "a", "b", [[100, 20], [300, 20]], style={"strokeColor": "#ff0000"}),
        edge("e3", "a", "b", [[100, 30], [300, 30]],
             style={"strokeColor": "#ff0000", "dashed": "1", "strokeWidth": "2.5"}),
        edge("e4", "a", "b", [[100, 40], [300, 40]],
             style={"dashed": "1", "dashPattern": "4 4", "opacity": "40"}),
        edge("e5", "a", "b", [[100, 45], [300, 45]],
             style={"strokeColor": "#00f", "endArrow": "none", "exitX": "0.9"}),
    ], "EdgeStyles"),
    case("special characters in labels, ids and styles", [
        container("c&<\"'>", "Zone & <b>\"q\"</b> 'x'", [0, 0, 600, 300],
                  style={"note": "a&b<c>d\"e'f\ng\rh\ti"}),
        vertex("v1", ["A & B", "<tag attr=\"v\">", "it's"], [20, 40, 160, 80], parent="c&<\"'>"),
        vertex("v2", ["Åsa Ärlig Öberg", "blåbär på smörgås"], [220, 40, 160, 80],
               parent="c&<\"'>"),
        vertex("v3", ["line one\nline two\ttabbed\rcr"], [420, 40, 160, 80], parent="c&<\"'>"),
        vertex("v4", ["emoji-free but wide: ÅÄÖ åäö éèê ß ñ ç ø æ"], [20, 160, 200, 80]),
        container("c2", "Multi\nline\tlabel\r!", [0, 320, 600, 100]),
        edge("e&", "v1", "v2", [[180, 80], [220, 80]], ["a < b & b > c", "\"quoted\"", "5 → 6 ✓"]),
        edge("e2", "v2", "v1", [[220, 100], [180, 100]], ["two\nlines", "𝔘 astral 😀"],
             labelAt=[200, 90],
             style={"labelBackgroundColor": "#fff"}),
    ], "Special \"chars\" & <more> ö\nnl"),
    case("wrapping: long text, many lines, an overlong word, narrow and wide boxes", [
        vertex("a", ["one two three four five six seven eight nine ten"], [0, 0, 100, 80],
               style={"fontSize": "14"}),
        vertex("b", ["alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
                     "omicron pi rho sigma tau upsilon phi chi psi omega"], [120, 0, 140, 90]),
        vertex("c", ["Supercalifragilisticexpialidocious_and_then_some tail"], [280, 0, 90, 60]),
        vertex("d", ["tiny box needs eight columns at least"], [400, 0, 10, 10]),
        vertex("e", ["first line", "second line is rather longer than the first one is"],
               [430, 0, 150, 70]),
        vertex("f", ["   ", "x   y"], [600, 0, 80, 40]),
        vertex("g", ["wide"], [0, 120, 600, 40], style={"fontSize": "24"}),
        vertex("h", ["cyl one two three four five six seven"], [0, 200, 90, 90], shape="cylinder"),
        vertex("i", ["actor caption wraps under the figure maybe"], [120, 200, 50, 90],
               shape="actor"),
        vertex("j", ["x"], [250, 200, -40, 20]),
    ], "Wrap"),
    case("multi-line vertex label is centred on the middle", [
        vertex("a", ["one", "two", "three", "four", "five"], [0, 0, 120, 100]),
    ], "Lines"),
    case("the first custom point is not the box: label_at on a one-line box", [
        vertex("a", ["Alpha"], [10.5, 20.25, 99.99, 49.995]),
        vertex("b", ["Beta"], [210.5, 120.25, 99.99, 49.995]),
        edge("e", "a", "b", [[110.49, 45.2], [160, 45.2], [160, 145], [210.5, 145]], ["x"],
             labelAt=[160, 100]),
    ], "Fractional"),
    # --- errors ---
    case("error: a duplicate id", [
        vertex("a", [], [0, 0, 1, 1]), vertex("a", [], [0, 0, 1, 1])], "Err"),
    case("error: a duplicate id across kinds", [
        container("a", "", [0, 0, 1, 1]), edge("a", "a", "a", [[0, 0], [1, 1]])], "Err"),
    case("error: a reserved id 0", [vertex("0", [], [0, 0, 1, 1])], "Err"),
    case("error: a reserved id 1", [container("1", "x", [0, 0, 1, 1])], "Err"),
    case("error: a duplicate id holding both quote marks and a backslash", [
        vertex("a'b\"c\\d\ne", [], [0, 0, 1, 1]), vertex("a'b\"c\\d\ne", [], [0, 0, 1, 1])],
        "Err"),
    case("error: a duplicate id holding an apostrophe", [
        vertex("it's", [], [0, 0, 1, 1]), vertex("it's", [], [0, 0, 1, 1])], "Err"),
    case("error: an unknown shape", [vertex("a", [], [0, 0, 1, 1], shape="hexagon")], "Err"),
    case("error: an unknown shape with an apostrophe", [
        vertex("a", [], [0, 0, 1, 1], shape="it's")], "Err"),
    case("error: an edge with one point", [edge("e", "a", "b", [[0, 0]])], "Err"),
    case("error: an edge with no points", [edge("e", "a", "b", [])], "Err"),
    case("error: a parent that is not a container", [
        vertex("a", [], [0, 0, 1, 1]), vertex("b", [], [0, 0, 1, 1], parent="a")], "Err"),
    case("error: a parent that does not exist", [
        vertex("a", [], [0, 0, 1, 1], parent="ghost")], "Err"),
    case("error: an edge as parent", [
        vertex("a", [], [0, 0, 1, 1]), vertex("b", [], [0, 0, 1, 1]),
        edge("e", "a", "b", [[0, 0], [1, 1]]),
        vertex("c", [], [0, 0, 1, 1], parent="e")], "Err"),
    case("error: a containment cycle", [
        container("p", "", [0, 0, 1, 1], parent="q"),
        container("q", "", [0, 0, 1, 1], parent="p")], "Err"),
    case("error: a container its own parent", [
        container("p", "", [0, 0, 1, 1], parent="p")], "Err"),
    case("error: a cycle behind a healthy chain", [
        container("top", "", [0, 0, 9, 9]),
        container("a", "", [0, 0, 1, 1], parent="top"),
        container("x", "", [0, 0, 1, 1], parent="y"),
        container("y", "", [0, 0, 1, 1], parent="z"),
        container("z", "", [0, 0, 1, 1], parent="x")], "Err"),
    case("error: an edge to nothing", [
        vertex("a", [], [0, 0, 1, 1]), edge("e", "a", "ghost", [[0, 0], [1, 1]])], "Err"),
    case("error: an edge from nothing", [
        vertex("a", [], [0, 0, 1, 1]), edge("e", "ghost", "a", [[0, 0], [1, 1]])], "Err"),
    case("error: an edge to an edge", [
        vertex("a", [], [0, 0, 1, 1]), vertex("b", [], [0, 0, 1, 1]),
        edge("e", "a", "b", [[0, 0], [1, 1]]),
        edge("f", "a", "e", [[0, 0], [1, 1]])], "Err"),
    case("error: a font size that is not a number (svg only)", [
        vertex("a", ["x"], [0, 0, 50, 30], style={"fontSize": "big"})], "Err"),
    case("error: an opacity that is not a number (svg only)", [
        vertex("a", ["x"], [0, 0, 50, 30], style={"opacity": "it's"})], "Err"),
    case("error: an opacity that is not a number on an edge (svg only)", [
        vertex("a", ["x"], [0, 0, 50, 30]),
        edge("e", "a", "a", [[0, 0], [1, 1]], style={"opacity": ""})], "Err"),
    case("error: an arc size that is not a number (svg only)", [
        vertex("a", ["x"], [0, 0, 50, 30],
               style={"rounded": "1", "absoluteArcSize": "1", "arcSize": "1,5"})], "Err"),
    case("error: a spacing that is not a number on a container (svg only)", [
        container("k", "x", [0, 0, 50, 30], style={"spacingLeft": "left"})], "Err"),
    case("error: an edge font size that is not a number (svg only)", [
        vertex("a", ["x"], [0, 0, 50, 30]),
        edge("e", "a", "a", [[0, 0], [1, 1]], ["x"], style={"fontSize": "1 2"})], "Err"),
]


def main() -> None:
    cases = []
    for c in CASES:
        c = dict(c)
        c["expect"] = run(c)
        cases.append(c)
    OUT.write_text(json.dumps({"doc": DOC, "cases": cases}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    ok = sum(1 for c in cases if "drawio" in c["expect"])
    print(f"{len(cases)} cases ({ok} render, {len(cases) - ok} build errors) -> {OUT}")


if __name__ == "__main__":
    main()
