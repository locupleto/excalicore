"""Generate corpus/scene/*.json by EXECUTING excalicore.scene.

Run from python/:  python3 tools/gen_corpus_scene.py

Every ``expect`` is what the Python implementation returned for the case's
inputs, never worked out by hand. The TypeScript half and the Python tests
both replay the files. Cases that name a corpus ``scene`` or ``reply`` refer to
``corpus/scenes/<name>.json`` / ``corpus/replies/<name>.txt``.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from excalicore import scene  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "corpus"
OUT = CORPUS / "scene"


def _scene(name):
    return json.loads((CORPUS / "scenes" / f"{name}.json").read_text())["elements"]


def _reply(name):
    return (CORPUS / "replies" / f"{name}.txt").read_text()


def _kwargs(options):
    """Fixture option names (camelCase) to the Python keyword arguments."""
    out = {}
    for k, v in (options or {}).items():
        if k == "keep":
            out["keep"] = tuple(v)
        elif k == "opaque":
            out["opaque"] = frozenset(v)
        elif k == "maxPoints":
            out["max_points"] = v
        elif k == "maxCoord":
            out["max_coord"] = v
        else:
            raise KeyError(k)
    return out


def _plain(value):
    """Tuples to lists, via JSON, so a result compares with what a file holds."""
    return json.loads(json.dumps(value))


def _case(fn, name, call, **fields):
    case = {"fn": fn, "name": name}
    case.update(fields)
    try:
        case["expect"] = _plain(call())
    except ValueError:
        case["expect"] = {"throws": True}
    return case


def write(filename, doc, cases):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / filename).write_text(
        json.dumps({"doc": doc, "cases": cases}, indent=2) + "\n")
    print(f"{filename}: {len(cases)} cases")


# --- helpers for neutral inputs --------------------------------------------------

def box(i, x=0, y=0, w=100, h=50, **extra):
    return {"id": i, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
            "seed": 1, "version": 3, "versionNonce": 99, **extra}


def text(i, container, t, **extra):
    return {"id": i, "type": "text", "x": 5, "y": 5, "width": 40, "height": 20,
            "text": t, "containerId": container, **extra}


def part(i, instance, role=None, **extra):
    tag = {"name": "widget", "instance": instance}
    if role:
        tag["role"] = role
    cd = extra.pop("customData", {})
    return {"id": i, "type": extra.pop("type", "rectangle"),
            "x": extra.pop("x", 0), "y": extra.pop("y", 0),
            "width": extra.pop("width", 10), "height": extra.pop("height", 10),
            **extra, "customData": {"stencil": {**tag, **extra.pop("tag", {})}, **cd}}


# --- compact.json ------------------------------------------------------------------

def compact_cases():
    cases = []
    for name in sorted(p.stem for p in (CORPUS / "scenes").glob("*.json")):
        els = _scene(name)
        cases.append(_case("compact", f"the corpus scene {name}, default dialect",
                           lambda els=els: scene.compact(els), scene=name))
    els = _scene("freedraw")
    cases.append(_case("compact", "the corpus stroke with a tighter polyline budget",
                       lambda: scene.compact(els, max_points=8), scene="freedraw",
                       options={"maxPoints": 8}))
    els = _scene("bound-labels")
    cases.append(_case("compact", "bound labels, keeping only id, type and label",
                       lambda: scene.compact(els, keep=("id", "type", "label")),
                       scene="bound-labels", options={"keep": ["id", "type", "label"]}))
    els = _scene("image-and-files")
    cases.append(_case("compact", "images treated as ordinary elements when opaque is empty",
                       lambda: scene.compact(els, opaque=frozenset()),
                       scene="image-and-files", options={"opaque": []}))

    def neutral(name, elements, options=None):
        kw = _kwargs(options)
        extra = {"options": options} if options else {}
        cases.append(_case("compact", name, lambda: scene.compact(elements, **kw),
                           elements=elements, **extra))

    neutral("none compacts to nothing", None)
    neutral("an empty list compacts to nothing", [])
    neutral("anything that is not a dict is skipped",
            [1, "x", None, [1, 2], box("a")])
    neutral("a deleted element is not shown, nor a label that points at it",
            [box("a", isDeleted=True), text("t", "a", "ghost"), box("b")])
    neutral("a label folds into its container, preferring originalText, with its fontSize",
            [box("a"), text("t", "a", "wrapped\ntext", originalText="wrapped text", fontSize=20)])
    neutral("a label without a fontSize folds to text alone",
            [box("a"), text("t", "a", "plain", fontSize=0)])
    neutral("a container's own label wins over a bound text",
            [box("a", label={"text": "own"}), text("t", "a", "bound")])
    neutral("text bound to a container that is not on the board stays standalone",
            [box("a"), text("t", "nowhere", "orphan")])
    neutral("a bound text with no content folds to no label",
            [box("a"), text("t", "a", "")])
    neutral("two texts bound to one container: the later wins",
            [box("a"), text("t1", "a", "first"), text("t2", "a", "second")])
    neutral("an arrow with only an end binding keeps its start free and loses its points",
            [box("a"), box("b", x=300),
             {"id": "e", "type": "arrow", "x": 100, "y": 25, "points": [[0, 0], [200, 0]],
              "endBinding": {"elementId": "b", "focus": 0, "gap": 1}}])
    neutral("both ends bound",
            [box("a"), box("b", x=300),
             {"id": "e", "type": "arrow", "x": 100, "y": 25, "points": [[0, 0], [200, 0]],
              "startBinding": {"elementId": "a"}, "endBinding": {"elementId": "b"}}])
    neutral("a binding to a deleted element is dangling",
            [box("a", isDeleted=True),
             {"id": "e", "type": "arrow", "x": 0, "y": 0, "points": [[0, 0], [1, 1]],
              "startBinding": {"elementId": "a"}}])
    neutral("an element that is not an arrow is folded the same way",
            [box("a"), box("b", startBinding={"elementId": "a"}, points=[[0, 0]])])
    neutral("elements without an id are kept, and unknown keys are stripped",
            [{"type": "rectangle", "x": 1, "y": 2, "customThing": 1}, {"type": "text", "text": "hi"}])
    neutral("a duplicate id: the later element owns the id for binding",
            [box("a"), box("a", x=5),
             {"id": "e", "type": "arrow", "points": [[0, 0], [1, 1]], "startBinding": {"elementId": "a"}}])
    neutral("opaque rounds half to even, as Python's round does",
            [{"id": "i1", "type": "image", "x": 2.5, "y": 3.5, "width": 0.5, "height": 1.5, "fileId": "f"},
             {"id": "i2", "type": "image", "x": -0.5, "y": -1.5, "width": 2.4999, "height": 2.5001}])
    neutral("a custom opaque type is read-only geometry",
            [box("a"), {"id": "d", "type": "diamond", "x": 3, "y": 4, "width": 5, "height": 6}],
            {"opaque": ["diamond"]})
    neutral("a custom opaque type with a bound label keeps the label out",
            [{"id": "d", "type": "diamond", "x": 3, "y": 4, "width": 5, "height": 6},
             text("t", "d", "inside")],
            {"opaque": ["diamond"]})
    neutral("stencil instances come first, in first-seen order, even with numeric-looking ids",
            [box("plain"),
             part("a", "10", "body"), part("b", "2", "body"), part("c", "10"),
             box("plain2")])
    neutral("an element with no id is not swallowed by a placed one",
            [part("p", "g1", "body"), {"type": "rectangle", "x": 1, "y": 1}])
    neutral("a placed member without an id hides every id-less element",
            [{"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
              "customData": {"stencil": {"name": "w", "instance": "g1", "role": "body"}}},
             {"type": "rectangle", "x": 1, "y": 1}])
    neutral("a stroke inside a stencil instance is part of the instance",
            [part("body", "g1", "body", x=10, y=10, width=40, height=40),
             part("pen", "g1", type="freedraw", points=[[0, 0], [5, 5]])])
    neutral("a freedraw is summarised even when it is not in the opaque set",
            [{"id": "s", "type": "freedraw", "x": 0, "y": 0, "width": 4, "height": 4,
              "points": [[0, 0], [2, 3], [4, 4]]}],
            {"opaque": []})
    return cases


# --- strokes.json -------------------------------------------------------------------

def stroke_cases():
    cases = []

    def rdp(name, points, eps):
        cases.append(_case("rdp", name, lambda: scene.rdp(points, eps), points=points, eps=eps))

    rdp("fewer than three points pass through", [[0, 0], [5, 5]], 1)
    rdp("a straight run collapses to its ends", [[float(i), 0.0] for i in range(10)], 0.1)
    rdp("a spike above the tolerance is kept", [[0, 0], [5, 8], [10, 0]], 1)
    rdp("a bump below the tolerance is dropped", [[0, 0], [5, 0.5], [10, 0]], 1)
    rdp("coincident ends measure distance to the point", [[0, 0], [3, 4], [0, 0]], 1)
    rdp("a staircase at three tolerances", [[0, 0], [1, 1], [2, 0], [3, 1], [4, 0], [5, 1], [6, 0]], 0.5)
    rdp("the same staircase, coarser", [[0, 0], [1, 1], [2, 0], [3, 1], [4, 0], [5, 1], [6, 0]], 1.5)
    rdp("a wave", [[float(i), round(((i * 7) % 11) / 3, 3)] for i in range(30)], 0.8)
    rdp("no points", [], 1)
    fd = _scene("freedraw")[0]["points"]
    for eps in (1, 4, 16):
        cases.append(_case("rdp", f"the corpus stroke at tolerance {eps}",
                           lambda eps=eps: scene.rdp(fd, eps),
                           scene="freedraw", index=0, eps=eps))

    def stroke(name, element, options=None, **ref):
        kw = _kwargs(options)
        extra = {"options": options} if options else {}
        cases.append(_case("strokeSummary", name, lambda: scene.stroke_summary(element, **kw),
                           **({"element": element} if not ref else ref), **extra))

    stroke("the corpus stroke", _scene("freedraw")[0], scene="freedraw", index=0)
    stroke("the corpus stroke with a budget of 8", _scene("freedraw")[0],
           {"maxPoints": 8}, scene="freedraw", index=0)
    stroke("the corpus stroke with a budget of 3", _scene("freedraw")[0],
           {"maxPoints": 3}, scene="freedraw", index=0)
    ring = [[round(50 + 50 * c, 3), round(50 + 50 * s, 3)] for c, s in
            [(1, 0), (0.7, 0.7), (0, 1), (-0.7, 0.7), (-1, 0), (-0.7, -0.7), (0, -1), (0.7, -0.7), (0.99, -0.05)]]
    stroke("a hand-drawn circle is closed",
           {"id": "ring", "type": "freedraw", "x": 10, "y": 20, "width": 100, "height": 100,
            "strokeColor": "#e03131", "points": ring})
    stroke("a line is not closed",
           {"id": "line", "type": "freedraw", "x": 0, "y": 0, "width": 100, "height": 0,
            "points": [[0, 0], [50, 1], [100, 0]]})
    stroke("a stroke drawn right to left, in absolute coordinates",
           {"id": "rtl", "type": "freedraw", "x": 200, "y": 200, "width": 60, "height": 20,
            "points": [[0, 0], [-30, 10], [-60, 20]]})
    stroke("a single point has no polyline",
           {"id": "dot", "type": "freedraw", "x": 1.5, "y": 2.5, "width": 0, "height": 0,
            "points": [[0, 0]]})
    stroke("no points at all", {"id": "none", "type": "freedraw", "x": 5, "y": 6})
    stroke("points with bad entries are skipped",
           {"id": "bad", "type": "freedraw", "x": 0, "y": 0, "width": 10, "height": 10,
            "points": [[0, 0], "x", [1], [True, 1], [None, 2], [3, "4"], [2, 2, 0.5], [10, 10]]})
    stroke("a zero-sized box falls back to a unit diagonal",
           {"id": "flat", "type": "freedraw", "x": 0, "y": 0, "width": 0, "height": 0,
            "points": [[0, 0], [0.1, 0.1], [0.05, 0.02]]})
    stroke("positions round half to even",
           {"id": "half", "type": "freedraw", "x": 0.5, "y": 1.5, "width": 2.5, "height": 3.5,
            "points": [[0, 0], [1, 1], [2, 0.5]]})
    stroke("a missing id is null and a missing position is the origin",
           {"type": "freedraw", "width": 3, "height": 3, "points": [[0, 0], [3, 3]]})
    stroke("a budget of 2 keeps only the ends", _scene("freedraw")[0],
           {"maxPoints": 2}, scene="freedraw", index=0)
    stroke("a budget of 1 is an error", _scene("freedraw")[0],
           {"maxPoints": 1}, scene="freedraw", index=0)
    stroke("a budget of 0 is an error, even with no points", {"id": "none", "type": "freedraw"},
           {"maxPoints": 0})
    stroke("an empty strokeColor is left out",
           {"id": "c", "type": "freedraw", "strokeColor": "", "width": 3, "height": 3,
            "points": [[0, 0], [3, 3]]})
    return cases


# --- stencils.json ------------------------------------------------------------------

def stencil_cases():
    cases = []

    def inst(name, element):
        cases.append(_case("instanceOf", name, lambda: scene.instance_of(element), element=element))

    inst("an element carrying the tag", part("a", "g-1"))
    inst("an element with no customData", box("a"))
    inst("customData that is not an object", {"customData": [1]})
    inst("a stencil tag that is not an object", {"customData": {"stencil": "x"}})
    inst("a tag with no instance", {"customData": {"stencil": {"name": "n"}}})
    inst("an empty instance", {"customData": {"stencil": {"instance": ""}}})
    inst("a numeric instance is read as its string", {"customData": {"stencil": {"instance": 12}}})
    inst("the pre-contract stamp tags are not read",
         {"customData": {"stamp": "Operator", "stampGroup": "sg-77"}})

    def summary(name, instance, members, **ref):
        cases.append(_case("stencilSummary", name, lambda: scene.stencil_summary(instance, members),
                           instance=instance, **({"members": members} if not ref else ref)))

    for sc, ids in (("stencil-instances", ("g-c-itil", "g-c-cmdb")), ("instance-group", ("sg-77",))):
        els = _scene(sc)
        for gid in ids:
            members = [e for e in els if scene.instance_of(e) == gid]
            summary(f"instance {gid} of the corpus scene {sc}", gid, members, scene=sc)

    def tagged(i, role=None, frame=None, **extra):
        tag = {"name": "widget", "instance": "w1"}
        if role:
            tag["role"] = role
        if frame is not None:
            tag["frame"] = frame
        return {"id": i, "type": extra.pop("type", "rectangle"),
                "x": extra.pop("x", 0), "y": extra.pop("y", 0),
                "width": extra.pop("width", 10), "height": extra.pop("height", 10),
                **extra, "customData": {"stencil": tag, **extra.pop("cd", {})}}

    frame = {"dx": -10, "dy": -5, "sw": 2, "sh": 3}
    summary("a body with a frame reports the subject's box",
            "w1", [tagged("limb", "decoration", x=5, y=5, width=1, height=1),
                   tagged("b", "body", frame, x=20, y=30, width=40, height=10)])
    summary("a frame given as numeric strings still reads",
            "w1", [tagged("b", "body", {"dx": "1", "dy": " 2 ", "sw": "1.5", "sh": "2e0"},
                          x=20, y=30, width=40, height=10)])
    summary("a frame with a missing field falls back to the footprint",
            "w1", [tagged("b", "body", {"dx": 1, "dy": 2, "sw": 1}, x=20, y=30, width=40, height=10),
                   tagged("c", "decoration", x=0, y=0, width=5, height=5)])
    summary("a frame with a null field falls back to the footprint",
            "w1", [tagged("b", "body", {"dx": None, "dy": 2, "sw": 1, "sh": 1}, x=20, y=30, width=40, height=10)])
    summary("a frame that is not an object falls back",
            "w1", [tagged("b", "body", "wide", x=20, y=30, width=40, height=10)])
    summary("a body that is not first still supplies the frame",
            "w1", [tagged("a", "decoration", x=0, y=0, width=3, height=3),
                   tagged("b", "body", frame, x=100, y=100, width=10, height=10)])
    summary("without a body the footprint is the union of the parts' own x, y",
            "w1", [tagged("a", x=10.5, y=20.5, width=10, height=10),
                   tagged("b", x=40, y=5, width=2.5, height=100)])
    summary("a label part names the label, preferring originalText",
            "w1", [tagged("b", "body", x=0, y=0, width=10, height=10),
                   tagged("l", "label", type="text", text="wrapped", originalText="Orig")])
    summary("a label-role part wins over an earlier text",
            "w1", [tagged("t", type="text", text="first"),
                   tagged("l", "label", type="text", text="second")])
    summary("without a label role the first text is the label",
            "w1", [tagged("a"), tagged("t1", type="text", text="one"), tagged("t2", type="text", text="two")])
    summary("a label carried as a property on the body counts",
            "w1", [tagged("b", "body", label={"text": "Carried"})])
    summary("a label property that is not an object is ignored",
            "w1", [tagged("b", "body", label="plain")])
    summary("an empty label text is no label",
            "w1", [tagged("t", type="text", text=""), tagged("b", "body", label={"text": "fallback"})])
    summary("other namespaces become the subject; the stencil namespace does not",
            "w1", [tagged("b", "body", cd={"bastion": {"kind": "node", "key": "k"}, "extra": 1})])
    summary("a part with no stencil name reports a null name",
            "w1", [{"id": "n", "type": "rectangle", "x": 1, "y": 2, "width": 3, "height": 4,
                    "customData": {"stencil": {"instance": "w1"}}}])
    summary("positions round half to even",
            "w1", [tagged("a", x=0.5, y=1.5, width=2, height=3)])
    summary("a single member with no size",
            "w1", [{"id": "n", "customData": {"stencil": {"instance": "w1", "name": "n"}}}])

    def bbox_case(name, elements, **ref):
        cases.append(_case("bbox", name, lambda: scene.bbox(elements),
                           **({"elements": elements} if not ref else ref)))

    bbox_case("none", None)
    bbox_case("an empty list", [])
    bbox_case("two boxes", [box("a", 0, 0, 10, 10), box("b", 20, 30, 5, 5)])
    bbox_case("a line drawn right to left starts before its own x",
              [{"type": "line", "x": 100, "y": 100, "width": 50, "height": 0, "points": [[0, 0], [-50, 0]]},
               box("b", 100, 100, 10, 10)])
    bbox_case("entries that are not placed elements are skipped",
              [1, "x", None, {"type": "rectangle"}, {"x": 1}, {"x": "1", "y": 2}, box("a", 5, 5, 10, 20)])
    bbox_case("a boolean position counts as a number, and reads as zero",
              [{"x": True, "y": 3, "width": 4, "height": 5}])
    for sc in ("stencil-instances", "instance-group", "bound-labels"):
        bbox_case(f"the whole corpus scene {sc}", _scene(sc), scene=sc)
    return cases


# --- patch.json ---------------------------------------------------------------------

def patch_cases():
    cases = []

    def sane(name, element, options=None):
        kw = _kwargs(options)
        extra = {"options": options} if options else {}
        cases.append(_case("saneGeometry", name, lambda: scene.sane_geometry(element, **kw),
                           element=element, **extra))

    sane("no coordinates at all", {"type": "rectangle"})
    sane("ordinary numbers", {"x": 1, "y": -2.5, "width": 300, "height": 4})
    sane("a null is absent", {"x": None, "width": None})
    sane("a boolean is not a coordinate", {"x": True})
    sane("a string is not a coordinate", {"width": "10"})
    sane("a list is not a coordinate", {"height": [1]})
    sane("exactly the bound is fine", {"x": scene.MAX_COORD, "y": -scene.MAX_COORD})
    sane("one past the bound is not", {"y": scene.MAX_COORD + 1})
    sane("a negative past the bound is not", {"x": -scene.MAX_COORD - 0.5})
    sane("a tighter bound", {"x": 500}, {"maxCoord": 100})
    sane("a looser bound", {"x": 5_000_000}, {"maxCoord": 10_000_000})
    sane("only x, y, width and height are checked", {"x": 1, "points": [[1e12, 0]], "angle": 1e12})

    def valid(name, obj, options=None):
        kw = _kwargs(options)
        extra = {"options": options} if options else {}
        cases.append(_case("validPatch", name, lambda: scene.valid_patch(obj, **kw), obj=obj, **extra))

    valid("an element with a type", {"elements": [{"type": "rectangle", "x": 1, "y": 2}]})
    valid("an element with no type", {"elements": [{"x": 1, "y": 2}]})
    valid("an element with an empty type", {"elements": [{"type": "", "x": 1, "y": 2}]})
    valid("an element with a list for a type rejects the patch", {"elements": [{"type": ["rectangle"], "x": 1, "y": 2}]})
    valid("an element with an object for a type rejects the patch", {"elements": [{"type": {"a": 1}}]})
    valid("an element with a number for a type rejects the patch", {"elements": [{"type": 5}]})
    valid("a deletion alone", {"delete": ["n7"]})
    valid("deletions drop what is not a string", {"delete": ["a", 7, None, "b", ["c"]]})
    valid("an empty patch", {"elements": [], "delete": []})
    valid("an empty object", {})
    valid("not an object: a list", [{"type": "rectangle"}])
    valid("not an object: a string", "elements")
    valid("not an object: null", None)
    valid("not an object: a number", 3)
    valid("elements that is not a list counts as none", {"elements": {"type": "rectangle"}, "delete": ["a"]})
    valid("delete that is not a list counts as none", {"elements": [{"type": "line"}], "delete": "a"})
    valid("an element that is not an object rejects the patch", {"elements": [{"type": "line"}, "box"]})
    valid("one insane coordinate rejects the patch",
          {"elements": [{"type": "line", "x": 1}, {"type": "line", "x": 1e9}]})
    valid("opaque elements are dropped, the rest stands",
          {"elements": [{"type": "freedraw", "id": "s"}, {"type": "image", "id": "i"},
                        {"type": "stencil", "id": "t"}, {"type": "rectangle", "id": "r"}]})
    valid("a patch of opaque elements alone says nothing",
          {"elements": [{"type": "freedraw", "id": "s"}]})
    valid("opaque elements alone plus a deletion is still a patch",
          {"elements": [{"type": "image", "id": "i"}], "delete": ["x"]})
    valid("a custom opaque set", {"elements": [{"type": "rectangle", "id": "r"}, {"type": "line", "id": "l"}]},
          {"opaque": ["rectangle"]})
    valid("an empty opaque set lets a stroke through",
          {"elements": [{"type": "freedraw", "id": "s"}]}, {"opaque": []})
    valid("a placement", {"elements": [{"stencil": "cylinder", "x": 240, "y": 180, "label": "Orders"}]})
    valid("a placement missing y", {"elements": [{"stencil": "cylinder", "x": 1}]})
    valid("a placement with a string coordinate", {"elements": [{"stencil": "cylinder", "x": "1", "y": 2}]})
    valid("a placement with a boolean coordinate", {"elements": [{"stencil": "cylinder", "x": True, "y": 2}]})
    valid("a blank stencil name is not a placement, and with no type rejects", {"elements": [{"stencil": "   ", "x": 1, "y": 2}]})
    valid("a Unicode-space-only stencil name is blank",
          {"elements": [{"stencil": "  　", "x": 1, "y": 2}]})
    valid("an information-separator stencil name is blank to Python",
          {"elements": [{"stencil": "\u001c\u0085", "x": 1, "y": 2}]})
    valid("a byte-order mark is not whitespace to Python",
          {"elements": [{"stencil": "﻿", "x": 1, "y": 2}]})
    valid("a blank stencil name beside a type is an ordinary element",
          {"elements": [{"stencil": " ", "type": "rectangle"}]})
    valid("a non-string stencil name falls back to the type",
          {"elements": [{"stencil": 5, "type": "rectangle"}]})
    valid("the old stamp placement is refused", {"elements": [{"stamp": "Operator", "x": 1, "y": 2}]})
    valid("a placement is bound by the same limit",
          {"elements": [{"stencil": "Operator", "x": scene.MAX_COORD + 1, "y": 0}]})
    valid("a placement under a tighter limit",
          {"elements": [{"stencil": "Operator", "x": 500, "y": 0}]}, {"maxCoord": 100})
    valid("extra keys on the patch are dropped",
          {"elements": [{"type": "line"}], "note": "hi", "delete": ["z"]})

    def extract(name, call_message, options=None, **ref):
        kw = _kwargs(options)
        extra = {"options": options} if options else {}
        cases.append(_case("extractPatch", name,
                           lambda: dict(zip(("prose", "patch"), scene.extract_patch(call_message, **kw))),
                           **(ref or {"message": call_message}), **extra))

    for name in sorted(p.stem for p in (CORPUS / "replies").glob("*.txt")):
        extract(f"the corpus reply {name}", _reply(name), reply=name)
    extract("the corpus reply echoes-opaque with nothing opaque", _reply("echoes-opaque"),
            {"opaque": []}, reply="echoes-opaque")
    extract("the corpus reply fenced-patch under a tight bound", _reply("fenced-patch"),
            {"maxCoord": 300}, reply="fenced-patch")

    P = '{"elements": [{"id": "a", "type": "rectangle", "x": 1, "y": 2}]}'
    extract("an empty message", "")
    extract("whitespace only", " \n\t ")
    extract("a patch and nothing else", P)
    extract("a json label before an unfenced patch", "Done.\njson\n" + P)
    extract("an upper-case JSON label inside a fence", "Done.\n```JSON\n" + P + "\n```\nBye.")
    extract("a label in backticks", "Done. `excalidraw` " + P + " Bye")
    extract("a label with space before the fence", "Here you go.\n\n  ```  excalidraw\n" + P + "\n```")
    extract("a fence with CRLF line endings", "Here.\r\n```json\r\n" + P + "\r\n```\r\nThanks.")
    extract("a bare fence is stripped like a labelled one", "Here you go:\n```\n" + P + "\n```\nDone.")
    extract("a bare fence with no newline before the patch", "Here:```" + P + "```")
    extract("a list-typed element in a reply leaves the message whole",
            'Here: {"elements": [{"type": ["rectangle"]}]}')
    extract("a fence closing line with trailing spaces", "Ok.\n```\n" + P + "\n```   \nNext.")
    extract("prose ending in the word json is not a label unless it ends there",
            "I prefer json for this. " + P + " Fine.")
    extract("the word json at the very end of the head is taken as a label",
            "I prefer json\n" + P)
    extract("braces in prose that are not JSON", "The set {a, b} is small. " + P)
    extract("a patch inside a larger valid object is not examined",
            '{"wrapper": ' + P + '}')
    extract("a patch inside a broken object is found",
            '{"wrapper": ' + P + ', "oops": ')
    extract("a brace inside a JSON string does not end the object",
            '{"elements": [{"type": "text", "text": "a } b { c", "x": 1, "y": 1}]} done')
    extract("escapes and non-ASCII in strings",
            'Se här: {"elements": [{"type": "text", "text": "caf\\u00e9 \\ud83d\\ude00 \\n \\"q\\" åäö \U0001F600", "x": 1, "y": 1}]}')
    extract("a trailing comma is not JSON", '{"elements": [{"type": "line"},]}')
    extract("a single-quoted object is not JSON", "{'elements': []}")
    extract("an unterminated string", '{"elements": [{"type": "line", "text": "oops}]}')
    extract("a raw newline inside a string is refused", '{"elements": [{"type": "text", "text": "a\nb"}]}')
    extract("a bad escape is refused", '{"elements": [{"type": "text", "text": "\\q"}]}')
    extract("a short unicode escape is refused", '{"elements": [{"type": "text", "text": "\\u12"}]}')
    extract("a lone surrogate escape is accepted", '{"elements": [{"type": "text", "text": "\\ud800"}]}')
    extract("a leading-zero number is refused", '{"elements": [{"type": "line", "x": 01}]}')
    extract("numbers in every form",
            '{"elements": [{"type": "line", "x": -0, "y": 1.5e2, "width": 2E-2, "height": 10, "angle": -0.0}]}')
    extract("a fraction without digits is refused", '{"elements": [{"type": "line", "x": 1.}]}')
    extract("NaN as a coordinate rejects the patch", '{"elements": [{"type": "line", "x": NaN}]}')
    extract("a duplicate key: the later value wins",
            '{"elements": [{"type": "line", "x": 1, "x": 2, "y": 0}]}')
    extract("literals: true, false, null, nested",
            '{"elements": [{"type": "line", "locked": true, "isDeleted": false, "link": null, "groupIds": [], "meta": {"a": [1, {"b": null}]}}]}')
    extract("whitespace everywhere in the object",
            '{ "elements" :\n[ { "type" : "line" } ] ,\t"delete" : [ ] }')
    extract("two patches: the last valid wins, an invalid one after it does not displace it",
            P + '\nThen: {"elements": [{"id": "b", "type": "ellipse"}]}\nThen: {"elements": [{"x": 1}]} bye')
    extract("an empty patch after a good one does not displace it", P + ' {"elements": [], "delete": []}')
    extract("a deletion-only patch", 'Removing it. {"delete": ["n7", "n8"]}')
    extract("a patch of only opaque elements leaves the message whole",
            'Echo: {"elements": [{"id": "s", "type": "freedraw"}]}')
    extract("a patch in the middle: prose on both sides is joined",
            "Before the patch.\n" + P + "\nAfter the patch.")
    extract("a patch in the middle in a fence: prose on both sides is joined",
            "Before.\n```json\n" + P + "\n```\n\nAfter.")
    extract("a message that is only a patch in a fence", "```json\n" + P + "\n```")
    extract("Unicode whitespace around the patch is stripped as Python strips it",
            "  Hello　\n" + P + "\n Bye\u0085")
    extract("a byte-order mark is not stripped from the prose", "﻿Hello " + P)
    extract("an information separator at the edge is stripped", "\u001cHello\u001d " + P + " \u001eBye\u001f")
    extract("a deep nesting still parses", '{"elements": [{"type": "line", "a": ' + "[" * 40 + "]" * 40 + "}]}")
    extract("a placement in a reply",
            'Here. {"elements": [{"stencil": "server", "x": 10, "y": 20, "label": "API", "subject": {"app": {"id": 1}}}]}')
    extract("an opaque option applied to a reply",
            'x {"elements": [{"id": "r", "type": "rectangle", "x": 0, "y": 0}]}', {"opaque": ["rectangle"]})
    extract("a max coordinate option applied to a reply",
            'x {"elements": [{"id": "r", "type": "rectangle", "x": 5000, "y": 0}]}', {"maxCoord": 1000})
    return cases


def main():
    write("compact.json",
          "compact() executed from python/excalicore/scene.py. A case gives the raw canvas either inline "
          "(`elements`, possibly null) or as a corpus scene by name (`scene`), plus optional `options` "
          "(`keep`, `opaque` as lists, `maxPoints`); `expect` is the skeleton list, key order included "
          "(it is the order the prompt shows the fields in). Cases cover every corpus scene and the "
          "binding, label, stencil-instance and opaque-type rules.",
          compact_cases())
    write("strokes.json",
          "rdp() and strokeSummary() executed from python/excalicore/scene.py. rdp cases give `points` and "
          "`eps` (or `scene` + `index` for the corpus stroke's own points); strokeSummary cases give an "
          "`element` (or `scene` + `index`) and optional `options.maxPoints`. Rounded outputs use Python's "
          "round (half to even). `{\"throws\": true}` means the call raises.",
          stroke_cases())
    write("stencils.json",
          "instanceOf(), stencilSummary() and bbox() executed from python/excalicore/scene.py. "
          "stencilSummary cases give the `instance` id and its `members` inline, or a corpus `scene` whose "
          "elements carrying that instance are the members. bbox cases give `elements` (or a `scene`); "
          "`expect` is [width, height].",
          stencil_cases())
    write("patch.json",
          "saneGeometry(), validPatch() and extractPatch() executed from python/excalicore/scene.py. "
          "extractPatch cases give the model's `message` inline, or a corpus `reply` by name, and expect "
          "{prose, patch} with patch null when nothing valid parses. Options: `opaque` (list), `maxCoord`.",
          patch_cases())


if __name__ == "__main__":
    main()
