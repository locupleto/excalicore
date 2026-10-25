"""Generate corpus/fidelity/*.json by EXECUTING excalicore.fidelity.

Run from python/:  python3 tools/gen_corpus_fidelity.py

Every ``expect`` is what the Python implementation returned for the case's
inputs, never worked out by hand. Rows are written with the column names
Python's ``ElementRow`` has (``element_id`` and the rest), which is also what a
SQL cursor hands back. Cases that name a corpus ``scene`` read
``corpus/scenes/<name>.json`` (its ``elements`` and, for the asset cases, its
``files``).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from excalicore import fidelity  # noqa: E402

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "corpus"
OUT = CORPUS / "fidelity"


def _scene(name):
    return json.loads((CORPUS / "scenes" / f"{name}.json").read_text())


def _scene_names():
    return sorted(p.stem for p in (CORPUS / "scenes").glob("*.json"))


def _plain(value):
    return json.loads(json.dumps(value))


def _rows(rows):
    return [dataclasses.asdict(r) for r in rows]


def write(filename, doc, cases):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / filename).write_text(json.dumps({"doc": doc, "cases": cases}, indent=2) + "\n")
    print(f"{filename}: {len(cases)} cases")


def _kw(options):
    return {"anon_prefix": options["anonPrefix"]} if options and "anonPrefix" in options else {}


def explode_cases():
    cases = []

    def explode(name, elements=None, options=None, **ref):
        els = _scene(ref["scene"])["elements"] if ref else elements
        extra = {"options": options} if options else {}
        cases.append({"fn": "explode", "name": name, **(ref or {"elements": elements}), **extra,
                      "expect": _plain(_rows(fidelity.explode(els, **_kw(options))))})

    for sc in _scene_names():
        explode(f"the corpus scene {sc}", scene=sc)
    explode("none", None)
    explode("an empty list", [])
    explode("an element with every column", [
        {"id": "a", "type": "rectangle", "x": 1.5, "y": -2, "width": 100, "height": 40,
         "angle": 0.5, "seed": 7, "strokeColor": "#1e1e1e"}])
    explode("columns that are absent stay absent", [{"id": "a", "type": "rectangle", "x": 1, "y": 2}])
    explode("a null column stays in the remainder and null in the column", [
        {"id": "a", "type": "line", "x": None, "y": 3, "angle": None}])
    explode("an element without an id is keyed by its position", [
        {"type": "rectangle", "x": 1}, {"id": "b", "type": "text"}, {"type": "line"}])
    explode("an empty-string id is anonymous", [{"id": "", "type": "rectangle"}])
    explode("a non-string id is anonymous", [{"id": 5, "type": "rectangle"}, {"id": None, "type": "line"}])
    explode("anonymous keys use the prefix asked for", [{"type": "rectangle"}, {"type": "line"}],
            {"anonPrefix": "tmp:"})
    explode("an empty prefix", [{"type": "rectangle"}], {"anonPrefix": ""})
    explode("entries that are not objects are dropped, and z counts only what is kept",
            ["nonsense", None, 7, [1], {"id": "a", "type": "rectangle"}, {"id": "b", "type": "line"}])
    explode("a missing or empty type is the empty string", [{"id": "a"}, {"id": "b", "type": ""}, {"id": "c", "type": None}])
    explode("a numeric type is its string", [{"id": "a", "type": 5}])
    explode("the remainder is json.dumps text: separators, key order, nesting", [
        {"id": "a", "type": "rectangle", "zeta": 1, "alpha": [1, 2, {"k": None}], "flag": True,
         "other": False, "nested": {"b": {"c": []}, "a": {}}}])
    explode("non-ASCII is escaped as json.dumps escapes it", [
        {"id": "a", "type": "text", "text": "café — \U0001F600 åäö", "emoji": "😀"}])
    explode("control characters, quotes, backslashes and DEL", [
        {"id": "a", "type": "text", "text": "a\"b\\c\nd\re\tf\bg\fh\u0001i\u001fj\u007fk/l"}])
    explode("keys are escaped like strings", [{"id": "a", "type": "text", "ke\"yé": 1}])
    explode("floats print as Python prints them", [
        {"id": "a", "type": "rectangle", "f1": 0.1, "f2": 123.456, "f3": -0.5, "f4": 1.5e-7, "f5": 0.00001,
         "f6": 0.0001, "f7": 1.2345678901234567, "f8": 3.5714285714285716, "f9": 12345678.9,
         "f10": 1e-5, "f11": 1.5e300, "f12": 2.5e-10, "f13": 99999999999999.9, "f14": 123456789012345.6}])
    explode("integers print as integers, large ones in full", [
        {"id": "a", "type": "rectangle", "i1": 0, "i2": -7, "i3": 1700000000000, "i4": 9007199254740991}])
    explode("a lone surrogate is escaped", [{"id": "a", "type": "text", "text": "\ud800"}])
    explode("empty containers", [{"id": "a", "type": "group", "list": [], "obj": {}, "s": ""}])
    return cases


def reassemble_cases():
    cases = []

    def reassemble(name, rows, options=None):
        extra = {"options": options} if options else {}
        cases.append({"fn": "reassemble", "name": name, "rows": rows, **extra,
                      "expect": _plain(fidelity.reassemble(rows, **_kw(options)))})

    def row(element_id="a", z=0, type="rectangle", json_text="{}", anonymous=0, **cols):
        r = {"element_id": element_id, "z": z, "type": type,
             "x": None, "y": None, "width": None, "height": None, "angle": None,
             "json": json_text, "anonymous": anonymous}
        r.update(cols)
        return r

    for sc in _scene_names():
        els = _scene(sc)["elements"]
        cases.append({"fn": "roundTrip", "name": f"the corpus scene {sc} survives exactly", "scene": sc,
                      "expect": fidelity.reassemble(fidelity.explode(els)) == els})
        cases.append({"fn": "roundTrip", "name": f"the corpus scene {sc} survives exactly when rows arrive reversed",
                      "scene": sc, "reversed": True,
                      "expect": fidelity.reassemble(list(reversed(fidelity.explode(els)))) == els})
    inline = [
        {"id": "a", "type": "rectangle", "x": 1.5, "y": 2, "width": 3, "height": 4, "angle": 0.25, "seed": 9,
         "boundElements": [{"id": "t", "type": "text"}], "future": {"deep": [1, {"x": None}]}},
        {"type": "line", "x": None, "y": None},
        {"id": "c", "type": "text", "angle": None, "text": "café"},
    ]
    cases.append({"fn": "roundTrip", "name": "inline elements: nulls, anonymous, unknown fields, non-ASCII",
                  "elements": inline, "expect": fidelity.reassemble(fidelity.explode(inline)) == inline})

    reassemble("none", None)
    reassemble("no rows", [])
    reassemble("a row with typed columns", [row("a", 0, "rectangle", '{"seed": 9}', x=1, y=2, width=3, height=4, angle=0.5)])
    reassemble("a zero column is a value, not an absence", [row("a", 0, "rectangle", "{}", x=0, y=0, width=0, height=0, angle=0)])
    reassemble("rows come back in z order, whatever order they arrive in",
               [row("c", 2), row("a", 0), row("b", 1)])
    reassemble("equal z keeps arrival order", [row("a", 1), row("b", 1), row("c", 0)])
    reassemble("a missing z sorts as zero", [row("a", 3), {"element_id": "b", "json": "{}"}])
    reassemble("an anonymous flag drops the key", [row("anon-0", 0, "line", "{}", anonymous=1)])
    reassemble("a fabricated key is recognised by its prefix alone", [row("anon-3", 0, "line", "{}", anonymous=0)])
    reassemble("a custom prefix", [row("tmp:0", 0, "line", "{}"), row("anon-1", 1, "line", "{}")], {"anonPrefix": "tmp:"})
    reassemble("the anonymous flag in its stored spellings",
               [row(f"k{i}", i, "r", "{}", anonymous=v) for i, v in enumerate([0, 1, "0", "1", "", True, False, None, 2])])
    reassemble("a null element_id gives no id", [row(None, 0, "line", "{}")])
    reassemble("a missing element_id gives no id", [{"z": 0, "json": "{}", "type": "line"}])
    reassemble("an id in the remainder survives when the key is anonymous",
               [row("anon-0", 0, "line", '{"id": null}', anonymous=1)])
    reassemble("the id column overrides the remainder", [row("real", 0, "line", '{"id": "stale"}')])
    reassemble("the type column overrides the remainder, an empty one does not",
               [row("a", 0, "ellipse", '{"type": "stale"}'), row("b", 1, "", '{"type": "kept"}')])
    reassemble("columns override the remainder only when they hold a value",
               [row("a", 0, "r", '{"x": 5, "y": 6}', x=1), row("b", 1, "r", '{"x": 5, "angle": null}')])
    reassemble("a corrupt remainder degrades to the columns", [row("a", 0, "rectangle", "{not json", x=5, y=6)])
    reassemble("a remainder that is not an object degrades to the columns",
               [row("a", 0, "r", "[1, 2]"), row("b", 1, "r", '"text"'), row("c", 2, "r", "null"), row("d", 3, "r", "7")])
    reassemble("an empty or null remainder is an empty element",
               [row("a", 0, "r", ""), row("b", 1, "r", None), {"element_id": "c", "z": 2, "type": "r"}])
    reassemble("whitespace around the remainder is fine", [row("a", 0, "r", ' \n {"k": 1}\t')])
    reassemble("a remainder with a duplicate key: the later wins", [row("a", 0, "r", '{"k": 1, "k": 2}')])
    reassemble("a remainder with escapes", [row("a", 0, "r", '{"t": "caf\\u00e9 \\ud83d\\ude00 \\n"}')])
    reassemble("extra keys on a row are ignored", [dict(row("a", 0, "r", '{"k": 1}'), extra="x", id=9)])
    return cases


def asset_cases():
    cases = []

    def ids(name, elements=None, **ref):
        els = _scene(ref["scene"])["elements"] if ref else elements
        cases.append({"fn": "fileIds", "name": name, **(ref or {"elements": elements}),
                      "expect": sorted(fidelity.file_ids(els))})

    def unref(name, elements=None, files=None, **ref):
        if ref:
            sc = _scene(ref["scene"])
            els, fls = sc["elements"], sc.get("files")
        else:
            els, fls = elements, files
        body = ref or {"elements": elements, "files": files}
        cases.append({"fn": "unreferencedFiles", "name": name, **body,
                      "expect": sorted(fidelity.unreferenced_files(els, fls))})

    for sc in _scene_names():
        ids(f"the corpus scene {sc}", scene=sc)
    for sc in _scene_names():
        unref(f"the corpus scene {sc}", scene=sc)
    ids("none", None)
    ids("an empty list", [])
    ids("a deleted element still holds its file",
        [{"id": "a", "type": "image", "fileId": "f1", "isDeleted": True}, {"id": "b", "type": "image", "fileId": "f2"}])
    ids("the same file twice counts once",
        [{"id": "a", "type": "image", "fileId": "f1"}, {"id": "b", "type": "image", "fileId": "f1"}])
    ids("falsy file ids are no reference",
        [{"fileId": None}, {"fileId": ""}, {"fileId": 0}, {"type": "rectangle"}, {"fileId": "ok"}])
    ids("a numeric file id is its string", [{"fileId": 12}])
    ids("entries that are not objects are skipped", ["x", None, 3, [1], {"fileId": "f"}])
    files = {"f1": {"mimeType": "image/png"}, "f2": {}, "f3": None}
    unref("some files referenced", [{"fileId": "f1"}], files)
    unref("every file referenced", [{"fileId": "f1"}, {"fileId": "f2"}, {"fileId": "f3"}], files)
    unref("no elements: every file is collectable", [], files)
    unref("no elements at all", None, files)
    unref("a reference to a file that is not stored changes nothing", [{"fileId": "ghost"}], files)
    unref("files that is not an object", [{"fileId": "f1"}], ["f1"])
    unref("files that is null", [{"fileId": "f1"}], None)
    unref("empty files", [{"fileId": "f1"}], {})
    return cases


def main():
    write("explode.json",
          "explode() executed from python/excalicore/fidelity.py. A case gives `elements` inline (or null), "
          "or a corpus `scene`, and optional `options.anonPrefix`; `expect` is the list of rows with the "
          "column names ElementRow has: element_id, z, type, x, y, width, height, angle, json, anonymous. "
          "`json` is the remainder's text exactly as json.dumps wrote it. Caveat for the TypeScript half: "
          "an integer-valued number is written as an integer there, because JavaScript has no float 2.0; "
          "no input here is a float with an integer value.",
          explode_cases())
    write("reassemble.json",
          "reassemble() and the round trip, executed from python/excalicore/fidelity.py. `reassemble` cases "
          "give `rows` as plain objects keyed by column name (what a SQL cursor returns) and expect the "
          "elements back. `roundTrip` cases give `elements` inline or a corpus `scene` (optionally with "
          "`reversed`: rows handed over in reverse order) and expect true when reassemble(explode(x)) "
          "equals x exactly.",
          reassemble_cases())
    write("assets.json",
          "file_ids() and unreferenced_files() executed from python/excalicore/fidelity.py. Cases give "
          "`elements` (and `files`) inline or a corpus `scene` (its elements and files); `expect` is the "
          "resulting set, sorted.",
          asset_cases())


if __name__ == "__main__":
    main()
