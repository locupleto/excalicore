"""Write ``corpus/elements/*.json`` by EXECUTING ``excalicore.elements``.

Every ``expect`` in those files is what the Python implementation returned
(and left behind in the objects it was given), never a value worked out by
hand. The TypeScript half reads the same files; the Python test suite
re-runs every case through :func:`run_case` and fails if the files have
drifted from the implementation.

Ids, nonces and the clock are replaced for each case (``excalicore.elements.
set_source``): ids ``id-0001``, ``id-0002`` ..., nonces 1, 2, 3 ..., clock
1700000000000. The inputs a case starts from (a scene to bind arrows in) are
built by the same builders under a different id prefix, ``src-``, so they never
collide with an id the call itself makes.

Run from ``python/``:  python3 tools/gen_corpus_elements.py
"""

from __future__ import annotations

import copy
import itertools
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from excalicore import elements as el  # noqa: E402
from excalicore import fontmetrics as fm  # noqa: E402

OUT = HERE.parents[1] / "corpus" / "elements"
CLOCK = 1_700_000_000_000
FONTS = (1, 2, 3, 5, 6)


# --- deterministic sources ---------------------------------------------------------------


def counting(prefix: str):
    n = itertools.count(1)
    return lambda: f"{prefix}{next(n):04d}"


def use_source(prefix: str) -> None:
    n = itertools.count(1)
    el.set_source(ids=counting(prefix), nonces=lambda: next(n), clock=lambda: CLOCK)


# --- normalising results -----------------------------------------------------------------


def norm(v: Any) -> Any:
    """JSON-ready: tuples as lists, floats to 6 decimals, whole floats as ints."""
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, float):
        r = round(v, 6)
        return int(r) if r.is_integer() else r
    return v


def ids_of(elements: list[dict]) -> list[str]:
    return [e["id"] for e in elements]


# --- running one case ---------------------------------------------------------------------

#: What each case may carry besides ``fn``, ``name`` and ``expect`` is that
#: function's inputs, spelled as the TypeScript API spells them.


def _kw(case: dict, *names: str) -> dict:
    return {n: case[n] for n in names if n in case}


def _snake(**pairs: Any) -> dict:
    return pairs


def run_case(case: dict) -> Any:
    """Execute one case against the Python implementation and return what
    ``expect`` should say. Inputs are copied first; the case is never changed."""
    c = copy.deepcopy({k: v for k, v in case.items() if k not in ("expect", "name")})
    use_source("id-")
    fn = c.pop("fn")
    try:
        return norm(_RUN[fn](c))
    except ValueError:
        return {"throws": True}


def _scene(c: dict) -> dict[str, dict]:
    return {e["id"]: e for e in c["elements"]}


def _end(v: dict | None):
    return None if v is None else (v["shape"], v["box"])


def r_bind_end(c: dict):
    by_id = _scene(c)
    arrow, host = by_id[c["arrow"]], (by_id[c["host"]] if c["host"] else None)
    kw = {"gap": c["gap"]} if "gap" in c else {}
    changed = el.bind_end(arrow, c["which"], host, by_id=by_id if c.get("byId") else None, **kw)
    return {"returns": ids_of(changed), "after": {"elements": c["elements"]}}


def r_refit(c: dict):
    by_id = _scene(c)
    kw = {"gap": c["gap"]} if "gap" in c else {}
    changed = el.refit_arrow(by_id[c["arrow"]], by_id, **kw)
    return {"returns": changed, "after": {"elements": c["elements"]}}


def r_detach(c: dict):
    by_id = _scene(c)
    gone, changed = el.detach(by_id[c["element"]], by_id)
    return {"returns": [gone, ids_of(changed)], "after": {"elements": c["elements"]}}


def r_add_label(c: dict):
    label = el.add_label(
        c["container"], c["text"], font=c["font"], roughness=c["roughness"],
        **_kw(c, "size", "padding"), **c.get("over", {}))
    return {"returns": label, "after": {"container": c["container"]}}


def r_fit_label(c: dict):
    changed = el.fit_label(c["container"], c["label"], **_kw(c, "text", "size", "padding"))
    return {"returns": ids_of(changed), "after": {"container": c["container"], "label": c["label"]}}


def r_label_of(c: dict):
    found = el.label_of(c["container"], _scene(c))
    return found["id"] if found else None


def r_route_between(c: dict):
    return el.route_between(c.get("points"), _end(c.get("start")), _end(c.get("end")), **_kw(c, "gap"))


def r_set_route(c: dict):
    el.set_route(c["linear"], c["route"])
    return {"returns": None, "after": {"linear": c["linear"]}}


def r_unlist(c: dict):
    got = el.unlist_bound(c["host"], c["memberId"])
    return {"returns": got, "after": {"host": c["host"]}}


def r_touch(c: dict):
    got = el.touch(c["element"])
    return {"returns": got, "after": {"element": c["element"]}}


def r_text_element(c: dict):
    return el.text_element(
        c["text"], c["x"], c["y"], font=c["font"], roughness=c["roughness"],
        container=c.get("container"), **_kw(c, "size", "padding"), **c.get("over", {}))


def r_frame(c: dict):
    return el.frame_element(c["x"], c["y"], c["w"], c["h"], c.get("frameName"),
                            **_kw(c, "roughness"), **c.get("over", {}))


def r_linear(c: dict):
    return el.linear_element(
        c["kind"], c["route"], roughness=c["roughness"], start_head=c.get("startHead"),
        end_head=c.get("endHead"), **c.get("over", {}))


def r_tables(c: dict):
    avg, widths = fm.METRICS[c["font"]]
    return {
        "codepoints": len(fm.CODEPOINTS),
        "average": avg,
        "glyphs": len(fm.ADVANCE[c["font"]]),
        "sum": sum(widths),
        "weighted": sum(i * w for i, w in enumerate(widths)) % 1_000_003,
    }


_RUN = {
    "lineHeight": lambda c: el.line_height(c["font"]),
    "textWidth": lambda c: el.text_width(c["line"], c["size"], c["font"], char_em=c.get("charEm")),
    "measureText": lambda c: el.measure_text(c["text"], c["size"], c["font"], char_em=c.get("charEm")),
    "wrapText": lambda c: el.wrap_text(c["text"], c["width"], c["size"], c.get("font", el.FONT_EXCALIFONT),
                                       char_em=c.get("charEm")),
    "textRoom": lambda c: el.text_room(c["container"], **_kw(c, "padding")),
    "containerHeightFor": lambda c: el.container_height_for(c["textHeight"], c["kind"], **_kw(c, "padding")),
    "baseElement": lambda c: el.base_element(c["kind"], c["x"], c["y"], c["w"], c["h"],
                                             roughness=c["roughness"], **c.get("over", {})),
    "textElement": r_text_element,
    "shapeElement": lambda c: el.shape_element(c["kind"], c["x"], c["y"], c["w"], c["h"],
                                               roughness=c["roughness"], **c.get("over", {})),
    "frameElement": r_frame,
    "linearElement": r_linear,
    "touch": r_touch,
    "boundaryPoint": lambda c: el.boundary_point(c["shape"], c["box"], c["aim"], **_kw(c, "gap")),
    "routeBetween": r_route_between,
    "routeOf": lambda c: el.route_of(c["linear"]),
    "setRoute": r_set_route,
    "unlistBound": r_unlist,
    "labelOf": r_label_of,
    "addLabel": r_add_label,
    "fitLabel": r_fit_label,
    "bindEnd": r_bind_end,
    "refitArrow": r_refit,
    "detach": r_detach,
    "tables": r_tables,
}


# --- building the cases --------------------------------------------------------------------


class Cases:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, fn: str, name: str, **inputs: Any) -> None:
        # The inputs are stored rounded, so they are run rounded: the expectation
        # is of what the file says, not of a few more decimals than it holds.
        case = norm({"fn": fn, "name": name, **inputs})
        case["expect"] = run_case(case)
        self.items.append(case)


def box(x: float, y: float, w: float, h: float) -> dict:
    return {"x": x, "y": y, "width": w, "height": h}


def container(kind: str, w: float, h: float, x: float = 100, y: float = 100) -> dict:
    return {"id": "box", "type": kind, "x": x, "y": y, "width": w, "height": h}


def src(build):
    """Run ``build`` with the ``src-`` id prefix and hand back what it made."""
    use_source("src-")
    return build()


def text_cases() -> Cases:
    k = Cases()
    for font in (*FONTS, 99):
        k.add("lineHeight", f"line height of font {font}" + (" (unknown, falls back)" if font == 99 else ""),
              font=font)

    words = [
        ("Hello", "a short ASCII word"),
        ("THE BASTION (proposed)", "capitals and punctuation, wider than the flat estimate"),
        ("iiii", "narrow glyphs"),
        ("MMMM", "wide glyphs"),
        ("Åsa Öberg lät åka äpplen", "Swedish letters from Latin-1"),
        ("café résumé naïve", "accents from Latin-1"),
        ("Łódź Žižek", "Latin Extended-A"),
        ("中文标签 label", "CJK ideographs, which take a full em"),
        ("日本語のラベル", "kana and kanji"),
        ("한국어", "Hangul syllables"),
        ("ＦＵＬＬ ｗｉｄｔｈ", "fullwidth Latin letters (East Asian width F)"),
        ("ｶﾅ half", "halfwidth katakana (East Asian width H, so narrow)"),
        ("Ping \U0001f600 pong", "an emoji outside the Basic Multilingual Plane"),
        ("☃ snowman ❤", "symbols the tables lack, narrow fallback"),
        ("é combining", "a combining mark counted as its own codepoint"),
        ("tab\there", "a tab, which the tables lack"),
        ("", "an empty string"),
        ("two\nlines", "a line break"),
        ("a\n\nb", "an empty line between"),
        ("\n", "only a line break"),
        ("Zero​width", "a zero-width space"),
    ]
    for text, what in words:
        for font in FONTS:
            k.add("measureText", f"{what}, font {font}, 20px", text=text, size=20, font=font)
    for text, what in words[:6] + words[7:8]:
        k.add("measureText", f"{what}, flat 0.55 em estimate", text=text, size=16, font=5, charEm=0.55)
    k.add("measureText", "an unknown font falls back to Excalifont's widths and Excalifont's line height factor 1.25",
          text="Fallback test", size=20, font=99)
    k.add("measureText", "28px text", text="Scaled headline", size=28, font=2)
    k.add("measureText", "a fractional size", text="Fractional", size=13.5, font=1)
    # Python rounds an exact tie to the even hundredth (0.125 -> 0.12, 0.375 -> 0.38); toFixed would not.
    for em in (0.125, 0.375, 0.625, 0.875, 1.125):
        k.add("measureText", f"a width of exactly {em}: the tie goes to the even hundredth",
              text="a", size=1, font=5, charEm=em)
    k.add("measureText", "a height of exactly 0.125: the tie goes to the even hundredth", text="a", size=0.1, font=5)
    k.add("measureText", "a 1.5 em flat estimate", text="wide", size=10, font=3, charEm=1.5)

    for line, what in (("MMMM", "capitals"), ("iiii", "narrow"), ("中文", "CJK"),
                       ("\U0001f600\U0001f600", "emoji"), ("", "empty")):
        for font in FONTS:
            k.add("textWidth", f"{what} line in font {font}", line=line, size=20, font=font)
        k.add("textWidth", f"{what} line, flat estimate counts codepoints", line=line, size=20, font=5, charEm=0.6)

    for text, width, size, font, what in (
        ("aaa bbb ccc ddd", 70, 20, 1, "words that fit are kept whole"),
        ("SUGGESTED ORDER OF WORK", 200, 20, 5, "capitals wrapped by pixels"),
        ("one\n\ntwo", 100, 20, 2, "line breaks and an empty line are kept"),
        ("x" * 25, 100, 20, 3, "a word wider than the box is broken"),
        ("anything", 1, 20, 5, "a box narrower than any glyph, one glyph a line"),
        ("A rather long label that cannot possibly fit on the one line", 120, 20, 6, "a long sentence in Nunito"),
        ("Åsa Öberg lät åka äpplen hem", 150, 20, 5, "Swedish letters"),
        ("中文标签中文标签中文", 100, 20, 5, "CJK wraps every five em"),
        ("\U0001f600" * 12, 100, 20, 5, "emoji are broken between codepoints, never within one"),
        ("mixed 中文 and words together", 130, 20, 2, "CJK among words"),
        ("two  spaces", 200, 20, 5, "a double space gives an empty word"),
        ("trailing ", 200, 20, 5, "a trailing space"),
        (" leading", 200, 20, 5, "a leading space"),
        ("", 100, 20, 5, "an empty string"),
        ("short", 1000, 20, 5, "room to spare"),
        ("éééééé", 40, 20, 5, "combining marks are codepoints too"),
        ("word " * 30, 301, 20, 5, "thirty short words in the room of an ellipse"),
    ):
        k.add("wrapText", f"{what}", text=text, width=width, size=size, font=font)
    k.add("wrapText", "the default font is Excalifont", text="aaa bbb ccc ddd eee", width=90, size=20)
    room = 10 * 20 * el.CHAR_EM
    for text, what in (("aaa bbb ccc ddd", "words kept whole"), ("one\n\ntwo", "breaks kept"),
                       ("x" * 25, "a long word broken")):
        k.add("wrapText", f"flat estimate: {what}", text=text, width=room, size=20, font=5, charEm=0.55)

    for kind in ("rectangle", "ellipse", "diamond", "frame", None):
        for w, h in ((440, 190), (200, 80), (101, 41), (90.5, 33.3)):
            k.add("textRoom", f"a {kind or 'typeless'} container {w} by {h}",
                  container=container(kind, w, h, 40, 960) if kind else
                  {"id": "box", "x": 40, "y": 960, "width": w, "height": h})
        k.add("textRoom", f"a {kind or 'typeless'} container with padding 0", container=container(kind, 200, 80), padding=0)
        k.add("textRoom", f"a {kind or 'typeless'} container with padding 8", container=container(kind, 200, 80), padding=8)
    for kind in ("rectangle", "ellipse", "diamond", None):
        for th in (23, 23.1, 45, 69.5, 0):
            k.add("containerHeightFor", f"text {th} high in a {kind or 'typeless'} container", textHeight=th, kind=kind)
        k.add("containerHeightFor", f"text 46 high in a {kind or 'typeless'} container, padding 12",
              textHeight=46, kind=kind, padding=12)
    return k


def metrics_cases() -> Cases:
    k = Cases()
    for font in FONTS:
        k.add("tables", f"the glyph table of font {font}: size, average, sum and a position-weighted checksum",
              font=font)
    # every width the tables hold, at the edges of each block, and the wide ranges' edges
    probes = [
        (" ", "space"), ("~", "the last ASCII glyph"), (" ", "no-break space, the first Latin-1 glyph"),
        ("­", "soft hyphen, a zero advance in some fonts"), ("ſ", "the last Latin Extended-A glyph"),
        ("ƀ", "the first codepoint past the tables"), ("\u007f", "DEL, between the blocks"),
        ("\u0080", "a C1 control, between the blocks"),
    ]
    for ch, what in probes:
        for font in (1, 5):
            k.add("textWidth", f"{what}, font {font}", line=ch, size=1000, font=font)
    wide = _wide_edges()
    for cp, what in wide:
        k.add("textWidth", f"U+{cp:04X}: {what}", line=chr(cp), size=1000, font=1)
    return k


def _wide_edges() -> list[tuple[int, str]]:
    """The first and last codepoint of every wide range, and the codepoint on
    each side of it, so a table that is off by one anywhere fails."""
    import unicodedata
    out: list[tuple[int, str]] = []
    start = None
    prev_wide = False
    ranges: list[tuple[int, int]] = []
    for cp in range(0x110000):
        w = unicodedata.east_asian_width(chr(cp)) in ("W", "F")
        if w and not prev_wide:
            start = cp
        if not w and prev_wide:
            ranges.append((start, cp - 1))
        prev_wide = w
    if prev_wide:
        ranges.append((start, 0x10FFFF))
    for lo, hi in ranges:
        # Only past the glyph tables (below U+0180 the table answers first).
        for cp, what in ((lo - 1, "just below a wide range"), (lo, "first of a wide range"),
                         (hi, "last of a wide range"), (hi + 1, "just above a wide range")):
            if 0x180 <= cp <= 0x10FFFF and not (0xD800 <= cp <= 0xDFFF):
                out.append((cp, what))
    seen: set[int] = set()
    return [(cp, w) for cp, w in out if not (cp in seen or seen.add(cp))]


def builder_cases() -> Cases:
    k = Cases()
    k.add("baseElement", "a bare rectangle with Excalidraw's defaults",
          kind="rectangle", x=10, y=20, w=300, h=120, roughness=1)
    k.add("baseElement", "overrides replace defaults, including the id",
          kind="rectangle", x=1, y=2, w=3, h=4, roughness=2,
          over={"strokeColor": "#fff", "id": "mine", "backgroundColor": "#a5d8ff", "customData": {"tag": "x"}})
    k.add("baseElement", "an ellipse at fractional coordinates",
          kind="ellipse", x=0.5, y=-12.25, w=80.75, h=40, roughness=0)
    k.add("baseElement", "a locked, rotated element",
          kind="diamond", x=0, y=0, w=60, h=60, roughness=0, over={"angle": 0.5, "locked": True, "opacity": 40})

    for font in FONTS:
        k.add("textElement", f"free text in font {font}", text="Hello world", x=5, y=6, font=font, roughness=0)
    k.add("textElement", "multi-line free text at 28px", text="First line\nSecond, longer line", x=0, y=0,
          size=28, font=5, roughness=1)
    k.add("textElement", "free text with a stroke colour and an id", text="Note", x=40, y=80, font=2, roughness=0,
          over={"strokeColor": "#e03131", "id": "note-1"})
    k.add("textElement", "Swedish text", text="Åsa Öberg", x=0, y=0, font=5, roughness=0)
    k.add("textElement", "CJK text", text="中文标签", x=0, y=0, font=5, roughness=0)
    for kind in ("rectangle", "ellipse", "diamond"):
        k.add("textElement", f"text wrapped and centred in a {kind}",
              text="Ingest service for incoming messages", x=0, y=0, font=5, roughness=0,
              container=container(kind, 200, 120))
    k.add("textElement", "text in a container with padding 10", text="Padded label", x=0, y=0, font=2, roughness=0,
          container=container("rectangle", 150, 60), padding=10)
    k.add("textElement", "text in a container at 16px", text="Small", x=0, y=0, size=16, font=6, roughness=0,
          container=container("rectangle", 150, 60))

    for kind in ("rectangle", "ellipse", "diamond"):
        k.add("shapeElement", f"a {kind}", kind=kind, x=10, y=20, w=200, h=100, roughness=1)
    k.add("shapeElement", "a filled, dashed rectangle", kind="rectangle", x=0, y=0, w=50, h=50, roughness=0,
          over={"backgroundColor": "#d0ebff", "strokeStyle": "dashed", "fillStyle": "hachure", "strokeWidth": 1})
    k.add("shapeElement", "a triangle is not a shape", kind="triangle", x=0, y=0, w=1, h=1, roughness=0)

    k.add("frameElement", "a named frame", x=0, y=0, w=300, h=200, frameName="Frame")
    k.add("frameElement", "an empty name is none", x=0, y=0, w=10, h=10, frameName="")
    k.add("frameElement", "no name at all, roughness 1", x=5, y=5, w=100, h=100, roughness=1)
    k.add("frameElement", "a frame in another colour", x=0, y=0, w=100, h=100, frameName="Zone",
          over={"strokeColor": "#1971c2"})

    k.add("linearElement", "an arrow along a right-angled route", kind="arrow",
          route=[[10, 20], [60, 20], [60, 70]], roughness=0, endHead="arrow")
    k.add("linearElement", "a line with no heads", kind="line", route=[[0, 0], [50, 20]], roughness=0)
    k.add("linearElement", "an arrow with a head at each end", kind="arrow", route=[[0, 0], [100, 0]],
          roughness=1, startHead="dot", endHead="triangle")
    k.add("linearElement", "an arrow right to left keeps its origin at the first point", kind="arrow",
          route=[[200, 50], [100, 50], [100, 10]], roughness=0, endHead="arrow")
    k.add("linearElement", "an elbow that doubles back has a positive extent", kind="arrow",
          route=[[0, 0], [100, 0], [100, 50], [20, 50]], roughness=0, endHead="arrow",
          over={"strokeStyle": "dashed", "strokeColor": "#2f9e44"})
    k.add("linearElement", "a single point", kind="arrow", route=[[5, 5]], roughness=0)
    k.add("linearElement", "a rectangle is not linear", kind="rectangle", route=[[0, 0], [1, 1]], roughness=0)

    for what, base in (("without a version", {"id": "t1"}),
                       ("at version 7", {"id": "t2", "version": 7, "versionNonce": 1, "updated": 1}),
                       ("with a null version", {"id": "t3", "version": None})):
        k.add("touch", f"an element {what}", element=base)
    k.add("touch", "a full element", element=src(lambda: el.shape_element("rectangle", 0, 0, 10, 10, roughness=0)))
    return k


def _scene_abc() -> list[dict]:
    """A rectangle at the origin, an ellipse to its right, a rectangle below, a free arrow."""
    def build():
        a = el.shape_element("rectangle", 0, 0, 100, 100, roughness=0)
        b = el.shape_element("ellipse", 300, 0, 100, 100, roughness=0)
        c = el.shape_element("rectangle", 0, 300, 100, 100, roughness=0)
        arrow = el.linear_element("arrow", [(0, 0), (1, 1)], roughness=0, end_head="arrow")
        return [a, b, c, arrow]
    return src(build)


def label_cases() -> Cases:
    k = Cases()
    for kind in ("rectangle", "ellipse", "diamond"):
        for text, what in (("Ingest", "a short label"),
                           ("A rather long label that cannot possibly fit on the one line", "a long label that grows the box"),
                           ("word " * 30, "thirty words")):
            for font in (5, 2):
                box_ = src(lambda: el.shape_element(kind, 100, 100, 200 if kind != "rectangle" else 120, 40,
                                                    roughness=0, strokeColor="#1971c2"))
                k.add("addLabel", f"{what} in a {kind}, font {font}", container=box_, text=text, font=font, roughness=0)
    k.add("addLabel", "a transparent stroke falls back to ink",
          container=src(lambda: el.shape_element("rectangle", 0, 0, 100, 50, roughness=0, strokeColor="transparent")),
          text="x", font=2, roughness=0)
    k.add("addLabel", "an explicit stroke colour wins",
          container=src(lambda: el.shape_element("rectangle", 0, 0, 100, 50, roughness=0, strokeColor="#1971c2")),
          text="Red", font=2, roughness=0, over={"strokeColor": "#e03131"})
    k.add("addLabel", "a box that already lists an arrow keeps it and appends the label",
          container=src(lambda: el.shape_element("rectangle", 0, 0, 200, 80, roughness=0,
                                                 boundElements=[{"id": "arrow-1", "type": "arrow"}])),
          text="Has an arrow", font=5, roughness=0)
    k.add("addLabel", "a 28px label with padding 12", container=src(lambda: el.shape_element("rectangle", 0, 0, 200, 60, roughness=0)),
          text="Bigger text label", font=6, roughness=1, size=28, padding=12)
    k.add("addLabel", "Swedish letters", container=src(lambda: el.shape_element("rectangle", 0, 0, 200, 80, roughness=0)),
          text="Åsa Öberg lät åka", font=5, roughness=0)
    k.add("addLabel", "CJK text", container=src(lambda: el.shape_element("rectangle", 0, 0, 120, 60, roughness=0)),
          text="中文标签中文标签中文", font=5, roughness=0)
    k.add("addLabel", "a label with a line break", container=src(lambda: el.shape_element("rectangle", 0, 0, 200, 100, roughness=0)),
          text="Line one\nLine two", font=2, roughness=0)
    k.add("addLabel", "an empty label", container=src(lambda: el.shape_element("rectangle", 0, 0, 200, 80, roughness=0)),
          text="", font=5, roughness=0)
    k.add("addLabel", "a label in a frame is laid out as a rectangle",
          container=src(lambda: el.frame_element(0, 0, 300, 200, "F")), text="In a frame", font=5, roughness=0)

    def labelled(kind: str, text: str, w: float = 200, h: float = 80, font: int = 5):
        def build():
            b = el.shape_element(kind, 100, 100, w, h, roughness=0)
            lab = el.add_label(b, text, font=font, roughness=0)
            return b, lab
        return src(build)

    b, lab = labelled("rectangle", "Ingest")
    b["x"], b["y"] = 400, 50
    k.add("fitLabel", "the box moved: the label follows", container=b, label=lab)
    b, lab = labelled("rectangle", "Ingest")
    k.add("fitLabel", "new text and size grow the box", container=b, label=lab, text="word " * 40, size=24)
    b, lab = labelled("rectangle", "Ingest")
    k.add("fitLabel", "new text only", container=b, label=lab, text="Something else")
    b, lab = labelled("rectangle", "Ingest")
    k.add("fitLabel", "new size only", container=b, label=lab, size=16)
    b, lab = labelled("rectangle", "word " * 20, 200, 80)
    b["width"] = 400
    k.add("fitLabel", "the box widened: the text re-wraps and the box does not shrink", container=b, label=lab)
    for kind in ("ellipse", "diamond"):
        b, lab = labelled(kind, "Gateway", 240, 120, 2)
        b["x"] = 0
        k.add("fitLabel", f"a {kind} moved", container=b, label=lab)
        b, lab = labelled(kind, "Gateway", 240, 60, 2)
        k.add("fitLabel", f"a {kind} that must grow", container=b, label=lab, text="word " * 30)
    b, lab = labelled("rectangle", "Ingest")
    k.add("fitLabel", "padding 10", container=b, label=lab, padding=10)

    b, lab = labelled("rectangle", "x")
    k.add("labelOf", "the text bound into a box", container=b, elements=[b, lab])
    k.add("labelOf", "a box whose label is not in the lookup", container=b, elements=[b])
    k.add("labelOf", "a box with no bound elements", container=src(lambda: el.shape_element("rectangle", 0, 0, 1, 1, roughness=0)),
          elements=[])
    arrow_box = src(lambda: el.shape_element("rectangle", 0, 0, 1, 1, roughness=0,
                                             boundElements=[{"id": "src-9999", "type": "arrow"}]))
    k.add("labelOf", "a box with only an arrow bound", container=arrow_box, elements=[arrow_box])

    host = src(lambda: el.shape_element("rectangle", 0, 0, 1, 1, roughness=0,
                                        boundElements=[{"id": "a", "type": "arrow"}, {"id": "t", "type": "text"}]))
    k.add("unlistBound", "a member that is listed, others remain", host=host, memberId="a")
    solo = src(lambda: el.shape_element("rectangle", 0, 0, 1, 1, roughness=0, boundElements=[{"id": "a", "type": "arrow"}]))
    k.add("unlistBound", "the only member: the list becomes null", host=solo, memberId="a")
    k.add("unlistBound", "a member that is not listed", host=copy.deepcopy(host), memberId="zzz")
    k.add("unlistBound", "a host with no list", host=src(lambda: el.shape_element("rectangle", 0, 0, 1, 1, roughness=0)),
          memberId="a")
    return k


def arrow_cases() -> Cases:
    k = Cases()
    bx = box(0, 0, 200, 100)  # centre (100, 50)
    aims = [("straight right", [500, 50]), ("straight left", [-300, 50]), ("straight down", [100, 400]),
            ("straight up", [100, -200]), ("diagonal", [300, 150]), ("a shallow slope", [600, 80]),
            ("a steep slope", [130, 600]), ("inside the shape", [110, 50]), ("at the centre", [100, 50]),
            ("just beside the centre", [100.0000001, 50])]
    for shape in ("rectangle", "ellipse", "diamond"):
        for what, aim in aims:
            k.add("boundaryPoint", f"a {shape}, aim {what}", shape=shape, box=bx, aim=aim)
        k.add("boundaryPoint", f"a {shape} with no gap", shape=shape, box=bx, aim=[300, 150], gap=0)
        k.add("boundaryPoint", f"a {shape} with a gap of 10", shape=shape, box=bx, aim=[300, 150], gap=10)
        k.add("boundaryPoint", f"a tall {shape}", shape=shape, box=box(50, 20, 60, 240), aim=[400, 40], gap=2)
    k.add("boundaryPoint", "an unknown shape is read as a rectangle", shape="text", box=bx, aim=[300, 150], gap=0)

    ra, rb = {"shape": "rectangle", "box": box(0, 0, 100, 100)}, {"shape": "rectangle", "box": box(300, 0, 100, 100)}
    ell, dia = {"shape": "ellipse", "box": box(300, 300, 120, 80)}, {"shape": "diamond", "box": box(0, 300, 100, 100)}
    k.add("routeBetween", "a free route is left as it is", points=[[0, 0], [10, 10]])
    k.add("routeBetween", "no points: the line between two boxes, trimmed", start=ra, end=rb, gap=0)
    k.add("routeBetween", "no points, default gap", start=ra, end=rb)
    k.add("routeBetween", "no points, a rectangle to an ellipse", start=ra, end=ell)
    k.add("routeBetween", "no points, a diamond to a rectangle", start=dia, end=rb)
    k.add("routeBetween", "only the end stands on a shape", points=[[0, 0], [500, 50]], end=rb, gap=0)
    k.add("routeBetween", "only the start stands on a shape", points=[[200, 50], [500, 50]], start=ra, gap=0)
    k.add("routeBetween", "a bent route keeps its bends",
          points=[[0, 0], [200, 0], [200, 350], [400, 350]], start=ra, end={"shape": "rectangle", "box": box(300, 300, 100, 100)},
          gap=0)
    k.add("routeBetween", "two points and two shapes are re-trimmed centre to centre",
          points=[[10, 10], [350, 40]], start=ra, end=rb)
    k.add("routeBetween", "a single point on a start shape lands on its centre", points=[[50, 50]], start=ra)
    k.add("routeBetween", "no points and only a start is an error", start=ra)
    k.add("routeBetween", "no points and nothing is an error")

    arrow = src(lambda: el.linear_element("arrow", [(10, 20), (60, 20), (60, 70)], roughness=0, end_head="arrow"))
    k.add("routeOf", "a bent arrow's absolute route", linear=arrow)
    k.add("routeOf", "an arrow with a fractional origin",
          linear=src(lambda: el.linear_element("arrow", [(0.5, 1.25), (10.75, 3)], roughness=0)))
    k.add("setRoute", "a new straight route", linear=copy.deepcopy(arrow), route=[[0, 0], [100, 40]])
    k.add("setRoute", "an elbow that doubles back", linear=copy.deepcopy(arrow),
          route=[[300, 100], [400, 100], [400, 160], [320, 160]])
    k.add("setRoute", "a route that runs up and left", linear=copy.deepcopy(arrow), route=[[200, 200], [100, 100]])

    # binding
    s = _scene_abc()
    a, b, c, arr = s
    k.add("bindEnd", "bind the start to a rectangle", elements=s, arrow=arr["id"], which="start", host=a["id"], byId=True)
    s = _scene_abc()
    a, b, c, arr = s
    el.bind_end(arr, "start", a, by_id={e["id"]: e for e in s})
    k.add("bindEnd", "binding the same end again changes nothing", elements=s, arrow=arr["id"], which="start",
          host=a["id"], byId=True)
    s = _scene_abc()
    a, b, c, arr = s
    el.bind_end(arr, "end", a, by_id={e["id"]: e for e in s})
    k.add("bindEnd", "rebinding takes the arrow out of the old host", elements=s, arrow=arr["id"], which="end",
          host=b["id"], byId=True)
    k.add("bindEnd", "rebinding without a lookup leaves the old host's list", elements=s, arrow=arr["id"], which="end",
          host=b["id"], byId=False)
    k.add("bindEnd", "freeing an end cleans its host", elements=s, arrow=arr["id"], which="end", host=None, byId=True)
    k.add("bindEnd", "a custom gap", elements=_scene_abc(), arrow=_scene_abc()[3]["id"], which="end",
          host=_scene_abc()[1]["id"], byId=True, gap=9)
    s = _scene_abc()
    a, b, c, arr = s
    b["boundElements"] = [{"id": "other", "type": "arrow"}]
    k.add("bindEnd", "a host that already has another arrow appends", elements=s, arrow=arr["id"], which="start",
          host=b["id"], byId=True)
    s = _scene_abc()
    a, b, c, arr = s
    el.bind_end(arr, "start", a, by_id={e["id"]: e for e in s})
    el.bind_end(arr, "end", a, by_id={e["id"]: e for e in s})
    k.add("bindEnd", "both ends on one host list it once", elements=s, arrow=arr["id"], which="end", host=a["id"], byId=True)
    k.add("bindEnd", "an end that is neither start nor end is an error", elements=_scene_abc(),
          arrow=_scene_abc()[3]["id"], which="middle", host=_scene_abc()[0]["id"], byId=False)

    def bound_pair(ax: float = 0, ay: float = 0, bx_: float = 300, by_: float = 0, kinds=("rectangle", "ellipse"),
                   route=None, start=True, end=True):
        def build():
            a_ = el.shape_element(kinds[0], ax, ay, 100, 100, roughness=0)
            b_ = el.shape_element(kinds[1], bx_, by_, 100, 100, roughness=0)
            arr_ = el.linear_element("arrow", route or [(0, 0), (1, 1)], roughness=0, end_head="arrow")
            idx = {e["id"]: e for e in (a_, b_, arr_)}
            if start:
                el.bind_end(arr_, "start", a_, by_id=idx)
            if end:
                el.bind_end(arr_, "end", b_, by_id=idx)
            return [a_, b_, arr_]
        return src(build)

    s = bound_pair()
    k.add("refitArrow", "both ends put on the edges of their shapes", elements=s, arrow=s[2]["id"])
    k.add("refitArrow", "a custom gap", elements=s, arrow=s[2]["id"], gap=0)
    s = bound_pair(by_=200)
    k.add("refitArrow", "after the ellipse moved down", elements=s, arrow=s[2]["id"])
    s = bound_pair(kinds=("diamond", "ellipse"), by_=-150, bx_=250)
    k.add("refitArrow", "a diamond to an ellipse above and right", elements=s, arrow=s[2]["id"])
    s = bound_pair(kinds=("rectangle", "diamond"), ay=250, bx_=40, by_=0)
    k.add("refitArrow", "a rectangle below a diamond", elements=s, arrow=s[2]["id"])
    s = bound_pair(route=[(0, 0), (150, 0), (150, 80), (300, 80)])
    k.add("refitArrow", "a bent route keeps its bends and moves its ends", elements=s, arrow=s[2]["id"])
    s = bound_pair(end=False)
    k.add("refitArrow", "only the start is bound", elements=s, arrow=s[2]["id"])
    s = bound_pair(start=False, route=[(50, 300), (320, 60)])
    k.add("refitArrow", "only the end is bound", elements=s, arrow=s[2]["id"])
    s = bound_pair(start=False, end=False)
    k.add("refitArrow", "an arrow bound at neither end is left alone", elements=s, arrow=s[2]["id"])
    s = bound_pair()
    s[1]["width"], s[1]["height"] = 200, 60
    k.add("refitArrow", "after the ellipse was resized", elements=s, arrow=s[2]["id"])
    s = bound_pair()
    k.add("refitArrow", "a shape missing from the lookup is skipped", elements=[s[0], s[2]], arrow=s[2]["id"])
    s = bound_pair(route=[(0, 0), (150, 0), (150, 80), (300, 80)])
    s[0]["x"], s[0]["y"] = -50, 20
    k.add("refitArrow", "a bent route after the start shape moved", elements=s, arrow=s[2]["id"])

    # detach
    def labelled_scene():
        def build():
            a_ = el.shape_element("rectangle", 0, 0, 100, 100, roughness=0)
            b_ = el.shape_element("ellipse", 300, 0, 100, 100, roughness=0)
            arr_ = el.linear_element("arrow", [(0, 0), (1, 1)], roughness=0, end_head="arrow")
            idx = {e["id"]: e for e in (a_, b_, arr_)}
            la = el.add_label(a_, "A", font=2, roughness=0)
            lb = el.add_label(b_, "B", font=2, roughness=0)
            idx[la["id"]] = la
            idx[lb["id"]] = lb
            el.bind_end(arr_, "start", a_, by_id=idx)
            el.bind_end(arr_, "end", b_, by_id=idx)
            return [a_, b_, arr_, la, lb]
        return src(build)

    s = labelled_scene()
    k.add("detach", "a box: its label goes, its arrow is let go at that end", elements=s, element=s[0]["id"])
    s = labelled_scene()
    k.add("detach", "the arrow leaves both hosts' lists", elements=s, element=s[2]["id"])
    s = labelled_scene()
    k.add("detach", "a label leaves its box's list", elements=s, element=s[3]["id"])
    s = labelled_scene()
    k.add("detach", "the other box", elements=s, element=s[1]["id"])
    s = labelled_scene()
    k.add("detach", "a box whose arrow is missing from the lookup", elements=[e for e in s if e["type"] != "arrow"],
          element=s[0]["id"])
    s = labelled_scene()
    k.add("detach", "an arrow whose hosts are missing from the lookup", elements=[s[2]], element=s[2]["id"])
    s = labelled_scene()
    s[3]["containerId"] = "gone"
    k.add("detach", "a label whose box is missing", elements=[e for e in s if e["id"] != s[0]["id"]], element=s[3]["id"])
    k.add("detach", "an element nothing refers to", elements=_scene_abc(), element=_scene_abc()[2]["id"])
    s = _scene_abc()
    s[2]["boundElements"] = [{"id": "ghost", "type": "arrow"}, {"id": "ghost-2", "type": "text"}]
    k.add("detach", "references to elements that are not there", elements=s, element=s[2]["id"])
    return k


# --- writing ---------------------------------------------------------------------------------


def dump(v: Any, depth: int = 0) -> str:
    """JSON with the cases and their keys one per line, the elements one per
    line, and everything below that on a single line."""
    pad = "  " * (depth + 1)
    end = "  " * depth
    if isinstance(v, dict) and depth <= 3 and v:
        body = ",\n".join(f"{pad}{json.dumps(k)}: {dump(x, depth + 1)}" for k, x in v.items())
        return "{\n" + body + "\n" + end + "}"
    if isinstance(v, list) and v and depth <= 4 and all(isinstance(x, dict) for x in v):
        return "[\n" + ",\n".join(pad + dump(x, depth + 1) for x in v) + "\n" + end + "]"
    return json.dumps(v, ensure_ascii=False)


DOCS = {
    "text": "measureText, textWidth, wrapText, textRoom, containerHeightFor and lineHeight, executed from python/excalicore/elements.py, "
            "across the five font families and an unknown one, Latin-1 and Latin Extended-A letters, CJK, fullwidth forms, emoji and "
            "symbols the glyph tables lack. Pure functions: each case is its inputs and an `expect` (a number, a [width, height] pair or "
            "a string). `charEm` is the opt-in flat estimate. Text is counted by codepoint, as Python counts it.",
    "fontmetrics": "The glyph tables of python/excalicore/fontmetrics.py: per font its size, average advance, sum and a position-weighted "
                   "checksum (`tables`), and single glyphs at 1000px (so the advance reads in thousandths of an em) at the edges of the "
                   "tables and of every East Asian wide range (`textWidth`): a glyph the tables lack is the font's average, or 1000 when wide.",
    "builders": "baseElement, textElement, shapeElement, frameElement, linearElement and touch. Every case runs under the counting source "
                "(ids id-0001..., nonces 1, 2, 3 ... in the order the builder asks for them, clock 1700000000000), so a whole built "
                "element is compared. `over` holds the keyword overrides. `{\"throws\": true}` means the call raises. touch's `expect` "
                "is {returns, after: {element}}.",
    "labels": "addLabel, fitLabel, labelOf and unlistBound. Mutating cases record `expect.returns` (the value returned; elements changed "
              "are given as ids) and `expect.after` (the inputs as the call left them: the container grows, the label moves). "
              "labelOf looks the label up in `elements` by id and returns its id or null.",
    "arrows": "boundaryPoint, routeBetween, routeOf, setRoute, bindEnd, refitArrow and detach. Scenes are plain lists of elements (built "
              "by the builders under ids src-0001...; the call's own ids are id-0001...) and are looked up by id. bindEnd/refitArrow/detach "
              "record `returns` (changed elements as ids; detach: [ids to remove, ids changed]) and `after.elements`, the whole scene as "
              "the call left it. `byId: false` on bindEnd passes no lookup.",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "text": text_cases(), "fontmetrics": metrics_cases(), "builders": builder_cases(),
        "labels": label_cases(), "arrows": arrow_cases(),
    }
    for name, cases in files.items():
        doc = {"doc": DOCS[name], "cases": norm(cases.items)}
        (OUT / f"{name}.json").write_text(dump(doc) + "\n")
        print(f"{name}.json: {len(cases.items)} cases")
    el.set_source()


if __name__ == "__main__":
    main()
