"""The elements module: complete Excalidraw elements, and references that stay
consistent when they change. Also the two geometry helpers it extended
(``wrap(verbatim=)`` and ``exit_t(shape=)``), whose defaults the corpus pins.

Beside the behaviour, one structural check: every element the module builds
carries every field Excalidraw's element types require. It is checked three
ways, strongest last: against a list written out here, against the fields of
the real captured elements in ``corpus/scenes``, and — when an Excalidraw
package is installed — against its own type declarations. Point
``EXCALIDRAW_PACKAGE`` at ``.../node_modules/@excalidraw/excalidraw`` (or have
it in ``node_modules`` at the repository root) and the last one runs; without
it, it skips.
"""

from __future__ import annotations

import math
import os
import pathlib
import re
import unittest
from typing import Any

from excalicore import elements as el
from excalicore import geometry
from excalicore.geometry import box_of

from . import corpus

# What Excalidraw 0.18 requires of every element, then of each family.
COMMON = (
    "id", "type", "x", "y", "width", "height", "angle", "strokeColor",
    "backgroundColor", "fillStyle", "strokeWidth", "strokeStyle", "roughness",
    "opacity", "groupIds", "frameId", "index", "roundness", "seed", "version",
    "versionNonce", "isDeleted", "boundElements", "updated", "link", "locked",
)
TEXT = ("text", "originalText", "fontSize", "fontFamily", "textAlign",
        "verticalAlign", "containerId", "lineHeight", "autoResize")
LINEAR = ("points", "lastCommittedPoint", "startBinding", "endBinding",
          "startArrowhead", "endArrowhead")
REQUIRED = {
    "rectangle": COMMON, "ellipse": COMMON, "diamond": COMMON,
    "frame": (*COMMON, "name"), "text": (*COMMON, *TEXT),
    "line": (*COMMON, *LINEAR), "arrow": (*COMMON, *LINEAR, "elbowed"),
}


def one_of_each() -> dict[str, dict]:
    return {
        "rectangle": el.shape_element("rectangle", 0, 0, 100, 50, roughness=1),
        "ellipse": el.shape_element("ellipse", 0, 0, 100, 50, roughness=1),
        "diamond": el.shape_element("diamond", 0, 0, 100, 50, roughness=1),
        "frame": el.frame_element(0, 0, 300, 200, "Frame"),
        "text": el.text_element("Hello", 5, 6, font=el.FONT_HELVETICA, roughness=0),
        "line": el.linear_element("line", [(0, 0), (50, 20)], roughness=0),
        "arrow": el.linear_element("arrow", [(0, 0), (50, 20)], roughness=0, end_head="arrow"),
    }


def close(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(a - b) < eps


class TestStructure(unittest.TestCase):
    def test_every_kind_carries_every_required_field(self) -> None:
        for kind, built in one_of_each().items():
            with self.subTest(kind):
                self.assertEqual(sorted(set(REQUIRED[kind]) - set(built)), [])
                self.assertEqual(built["type"], kind)

    def test_a_bound_label_is_complete_too(self) -> None:
        box = el.shape_element("rectangle", 0, 0, 200, 80, roughness=0)
        label = el.add_label(box, "Ingest", font=el.FONT_HELVETICA, roughness=0)
        self.assertEqual(sorted(set(REQUIRED["text"]) - set(label)), [])

    def test_no_field_is_invented_beyond_what_the_corpus_shows(self) -> None:
        """Against real captured elements: each kind has at least every field a
        captured one has (customData is the application's own)."""
        seen: dict[str, set[str]] = {}
        for name in ("arrow-bindings", "bound-labels", "instance-group"):
            for e in corpus.elements(name):
                seen.setdefault(e["type"], set()).update(set(e) - {"customData"})
        built = one_of_each()
        self.assertTrue({"rectangle", "ellipse", "text", "arrow", "line"} <= set(seen))
        for kind, captured in seen.items():
            if kind not in built:
                continue
            with self.subTest(kind):
                self.assertEqual(sorted(captured - set(built[kind])), [])

    def test_against_the_installed_excalidraw_types(self) -> None:
        path = _excalidraw_types()
        if path is None:
            self.skipTest("no @excalidraw/excalidraw installed (set EXCALIDRAW_PACKAGE)")
        src = path.read_text()
        base = _type_fields(src, "_ExcalidrawElementBase")
        self.assertIn("seed", base)
        want = {
            "rectangle": base, "ellipse": base, "diamond": base,
            "frame": base | _type_fields(src, "ExcalidrawFrameElement"),
            "text": base | _type_fields(src, "ExcalidrawTextElement"),
            "line": base | _type_fields(src, "ExcalidrawLinearElement"),
            "arrow": (base | _type_fields(src, "ExcalidrawLinearElement")
                      | _type_fields(src, "ExcalidrawArrowElement")),
        }
        for kind, built in one_of_each().items():
            with self.subTest(kind):
                self.assertEqual(sorted(want[kind] - {"type"} - set(built)), [])
                # and nothing Excalidraw does not know (a typo would pass silently)
                self.assertEqual(sorted(set(built) - want[kind] - {"customData", "type"}), [])


def _excalidraw_types() -> pathlib.Path | None:
    roots = []
    if os.environ.get("EXCALIDRAW_PACKAGE"):
        roots.append(pathlib.Path(os.environ["EXCALIDRAW_PACKAGE"]))
    roots.append(corpus.ROOT.parent / "node_modules" / "@excalidraw" / "excalidraw")
    for root in roots:
        found = root / "dist" / "types" / "excalidraw" / "element" / "types.d.ts"
        if found.is_file():
            return found
    return None


def _type_fields(src: str, name: str) -> set[str]:
    """The required top-level keys of the object type ``name`` is declared as."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    m = re.search(rf"type {re.escape(name)} = [^{{]*?\{{", src)
    assert m, name
    depth, top, i = 1, [], m.end()
    while depth and i < len(src):
        c = src[i]
        depth += (c == "{") - (c == "}")
        if depth == 1 and c != "}":
            top.append(c)
        i += 1
    return {k for k, optional in re.findall(r"(?m)^\s*(\w+)(\??):", "".join(top)) if not optional}


class TestBase(unittest.TestCase):
    def test_overrides_replace_defaults_and_ids_are_fresh(self) -> None:
        a = el.base_element("rectangle", 1, 2, 3, 4, roughness=2, strokeColor="#fff", id="mine")
        b = el.base_element("rectangle", 1, 2, 3, 4, roughness=2)
        self.assertEqual((a["id"], a["strokeColor"], a["roughness"]), ("mine", "#fff", 2))
        self.assertNotEqual(a["seed"], b["seed"])
        self.assertEqual(len(b["id"]), 21)
        self.assertIsNone(b["index"])

    def test_touch_moves_the_version_on(self) -> None:
        e = el.base_element("rectangle", 0, 0, 1, 1, roughness=0, version=7, versionNonce=1, updated=1)
        el.touch(e)
        self.assertEqual(e["version"], 8)
        self.assertNotEqual(e["versionNonce"], 1)
        self.assertGreater(e["updated"], 1)

    def test_shapes_have_their_roundness(self) -> None:
        self.assertEqual(el.shape_element("rectangle", 0, 0, 1, 1, roughness=0)["roundness"], {"type": 3})
        self.assertEqual(el.shape_element("diamond", 0, 0, 1, 1, roughness=0)["roundness"], {"type": 2})
        self.assertIsNone(el.shape_element("ellipse", 0, 0, 1, 1, roughness=0)["roundness"])
        with self.assertRaises(ValueError):
            el.shape_element("triangle", 0, 0, 1, 1, roughness=0)

    def test_a_frame_has_the_frame_outline_and_an_optional_name(self) -> None:
        f = el.frame_element(0, 0, 10, 10, "")
        self.assertEqual((f["strokeColor"], f["name"], f["roughness"]), (el.FRAME_INK, None, 0))

    def test_linear_origin_is_the_first_point(self) -> None:
        a = el.linear_element("arrow", [(10, 20), (60, 20), (60, 70)], roughness=0, end_head="arrow")
        self.assertEqual((a["x"], a["y"], a["width"], a["height"]), (10, 20, 50, 50))
        self.assertEqual(a["points"], [[0, 0], [50, 0], [50, 50]])
        self.assertEqual(el.route_of(a), [(10, 20), (60, 20), (60, 70)])
        self.assertIs(a["elbowed"], False)
        self.assertNotIn("elbowed", el.linear_element("line", [(0, 0), (1, 1)], roughness=0))


class TestText(unittest.TestCase):
    def test_measure_counts_widest_line_and_lines(self) -> None:
        w, h = el.measure_text("ab\nabcd", 20, el.FONT_HELVETICA, char_em=el.CHAR_EM)
        self.assertAlmostEqual(w, 4 * 20 * el.CHAR_EM)
        self.assertAlmostEqual(h, 2 * 20 * 1.15)
        self.assertEqual(el.measure_text("", 20, el.FONT_EXCALIFONT)[0], 20 * el.CHAR_EM)

    def test_wrap_keeps_breaks_and_breaks_a_long_word(self) -> None:
        room = 10 * 20 * el.CHAR_EM                     # ten columns
        wrap_text = el.wrap_text
        el_wrap = lambda t, w, s: wrap_text(t, w, s, char_em=el.CHAR_EM)  # noqa: E731
        self.assertEqual(el_wrap("aaa bbb ccc ddd", room, 20), "aaa bbb\nccc ddd")
        self.assertEqual(el_wrap("one\n\ntwo", room, 20), "one\n\ntwo")
        self.assertEqual(el_wrap("x" * 25, room, 20), "x" * 10 + "\n" + "x" * 10 + "\n" + "x" * 5)
        self.assertEqual(el_wrap("anything", 1, 20), "a\nn\ny\nt\nh\ni\nn\ng")


    def test_measure_uses_the_glyph_widths_of_the_font(self) -> None:
        # Excalifont's capitals are wider than the old flat 0.55 em: the labels
        # that rendered clipped on the Observatory whiteboard.
        for label, true_width in (("THE BASTION (proposed)", 260.2), ("NOTES & PUSHBACK", 208.1),
                                  ("SUGGESTED ORDER", 214.2)):
            w, _ = el.measure_text(label, 20, el.FONT_EXCALIFONT)
            self.assertGreater(w, len(label) * 20 * el.CHAR_EM, label)
            self.assertAlmostEqual(w, true_width, delta=0.2, msg=label)
        caps = el.measure_text("MMMM", 20, el.FONT_EXCALIFONT)[0]
        lows = el.measure_text("iiii", 20, el.FONT_EXCALIFONT)[0]
        self.assertGreater(caps, 2.5 * lows)
        # a monospace font stays flat; an unknown glyph falls back, never zero
        self.assertEqual(el.measure_text("MMMM", 20, el.FONT_CASCADIA)[0],
                         el.measure_text("iiii", 20, el.FONT_CASCADIA)[0])
        self.assertGreater(el.measure_text("\u2603", 20, el.FONT_EXCALIFONT)[0], 0)
        self.assertEqual(el.measure_text("\u4e2d", 20, el.FONT_EXCALIFONT)[0], 20)

    def test_wrap_by_pixels_keeps_capitals_inside_the_box(self) -> None:
        wrapped = el.wrap_text("SUGGESTED ORDER OF WORK", 200, 20, el.FONT_EXCALIFONT)
        for line in wrapped.split("\n"):
            self.assertLessEqual(el.text_width(line, 20, el.FONT_EXCALIFONT), 200, line)
        self.assertEqual(wrapped.replace("\n", " "), "SUGGESTED ORDER OF WORK")

    def test_free_text_and_contained_text(self) -> None:
        t = el.text_element("Hello", 5, 6, size=20, font=el.FONT_HELVETICA, roughness=0)
        self.assertEqual((t["x"], t["y"], t["textAlign"], t["containerId"]), (5, 6, "left", None))
        box = {"id": "b", "x": 100, "y": 100, "width": 200, "height": 80}
        c = el.text_element("Hello", 0, 0, font=el.FONT_HELVETICA, roughness=0, container=box)
        self.assertEqual((c["containerId"], c["textAlign"], c["verticalAlign"]), ("b", "center", "middle"))
        self.assertTrue(close(c["x"] + c["width"] / 2, 200))
        self.assertTrue(close(c["y"] + c["height"] / 2, 140))


class TestLabels(unittest.TestCase):
    def labelled(self, text: str, w: float = 200, h: float = 80) -> tuple[dict, dict]:
        box = el.shape_element("rectangle", 100, 100, w, h, roughness=0, strokeColor="#1971c2")
        return box, el.add_label(box, text, font=el.FONT_HELVETICA, roughness=0)

    def test_the_label_is_bound_both_ways_and_centred(self) -> None:
        box, label = self.labelled("Ingest")
        self.assertEqual(label["containerId"], box["id"])
        self.assertEqual(box["boundElements"], [{"id": label["id"], "type": "text"}])
        self.assertEqual(label["strokeColor"], "#1971c2")
        self.assertTrue(close(label["x"] + label["width"] / 2, box["x"] + box["width"] / 2))

    def test_a_label_in_a_transparent_box_is_ink(self) -> None:
        box = el.shape_element("rectangle", 0, 0, 100, 50, roughness=0, strokeColor="transparent")
        self.assertEqual(el.add_label(box, "x", font=el.FONT_HELVETICA, roughness=0)["strokeColor"], el.INK)

    def test_a_long_label_wraps_and_the_box_grows(self) -> None:
        box, label = self.labelled("A rather long label that cannot possibly fit on the one line", 120, 30)
        self.assertGreater(label["text"].count("\n"), 1)
        self.assertEqual(box["width"], 120)
        self.assertGreaterEqual(box["height"], label["height"] + 2 * el.PADDING)
        self.assertTrue(close(label["y"] + label["height"] / 2, box["y"] + box["height"] / 2))

    def test_fit_label_follows_the_box_and_new_text(self) -> None:
        box, label = self.labelled("Ingest")
        box["x"], box["y"] = 400, 50
        changed = el.fit_label(box, label)
        self.assertEqual(changed, [label])
        self.assertTrue(close(label["x"] + label["width"] / 2, 500))
        changed = el.fit_label(box, label, text="word " * 40, size=24)
        self.assertEqual(label["originalText"], "word " * 40)
        self.assertEqual(label["fontSize"], 24)
        self.assertEqual(changed, [label, box])
        self.assertTrue(close(label["y"] + label["height"] / 2, box["y"] + box["height"] / 2))

    def test_label_of_finds_it(self) -> None:
        box, label = self.labelled("x")
        self.assertIs(el.label_of(box, {label["id"]: label}), label)
        self.assertIsNone(el.label_of(box, {}))


class TestEnds(unittest.TestCase):
    def test_boundary_of_each_shape(self) -> None:
        box = (0, 0, 200, 100)                           # centre (100, 50)
        # straight right: the edge for a rectangle, the vertex for the others, plus the gap
        for shape in ("rectangle", "ellipse", "diamond"):
            x, y = el.boundary_point(shape, box, (500, 50), gap=0)
            self.assertTrue(close(x, 200) and close(y, 50), (shape, x, y))
        # diagonal: a rectangle exits at its corner, an ellipse and a diamond sooner
        r = el.boundary_point("rectangle", box, (300, 150), gap=0)
        e = el.boundary_point("ellipse", box, (300, 150), gap=0)
        d = el.boundary_point("diamond", box, (300, 150), gap=0)
        self.assertEqual(r, (200, 100))
        self.assertTrue(close(math.hypot((e[0] - 100) / 100, (e[1] - 50) / 50), 1))
        self.assertTrue(close(abs(d[0] - 100) / 100 + abs(d[1] - 50) / 50, 1))
        self.assertLess(math.hypot(e[0] - 100, e[1] - 50), math.hypot(r[0] - 100, r[1] - 50))
        # the gap stands off the edge
        self.assertTrue(close(el.boundary_point("rectangle", box, (500, 50))[0], 200 + el.BIND_GAP))
        # an aim inside the shape stops at the aim; an aim at the centre is the centre
        self.assertEqual(el.boundary_point("rectangle", box, (110, 50), gap=0), (110, 50))
        self.assertEqual(el.boundary_point("rectangle", box, (100, 50)), (100, 50))

    def test_route_between_free_one_and_both_ends(self) -> None:
        a, b = ("rectangle", (0, 0, 100, 100)), ("rectangle", (300, 0, 100, 100))
        free = el.route_between([(0, 0), (10, 10)])
        self.assertEqual(free, [(0, 0), (10, 10)])
        both = el.route_between(None, a, b, gap=0)
        self.assertEqual(both, [(100, 50), (300, 50)])
        one = el.route_between([(0, 0), (500, 50)], None, b, gap=0)
        self.assertEqual(one[0], (0, 0))
        self.assertTrue(close(one[1][0], 300))                               # b's near edge, aimed at (0, 0)
        with self.assertRaises(ValueError):
            el.route_between(None, a, None)

    def test_a_bent_route_keeps_its_bends(self) -> None:
        a, b = ("rectangle", (0, 0, 100, 100)), ("rectangle", (300, 300, 100, 100))
        route = el.route_between([(0, 0), (200, 0), (200, 350), (400, 350)], a, b, gap=0)
        self.assertEqual(len(route), 4)
        self.assertEqual(route[1:3], [(200, 0), (200, 350)])


class TestBinding(unittest.TestCase):
    def scene(self) -> dict[str, dict]:
        a = el.shape_element("rectangle", 0, 0, 100, 100, roughness=0)
        b = el.shape_element("ellipse", 300, 0, 100, 100, roughness=0)
        c = el.shape_element("rectangle", 0, 300, 100, 100, roughness=0)
        arrow = el.linear_element("arrow", [(0, 0), (1, 1)], roughness=0, end_head="arrow")
        return {e["id"]: e for e in (a, b, c, arrow)}

    def parts(self, by_id: dict[str, dict]) -> tuple[dict, dict, dict, dict]:
        a, b, c, arrow = by_id.values()
        return a, b, c, arrow

    def test_bind_is_two_way_and_reports_the_host(self) -> None:
        by_id = self.scene()
        a, b, _c, arrow = self.parts(by_id)
        self.assertEqual(el.bind_end(arrow, "start", a, by_id=by_id), [a])
        self.assertEqual(arrow["startBinding"], {"elementId": a["id"], "focus": 0, "gap": el.BIND_GAP})
        self.assertEqual(a["boundElements"], [{"id": arrow["id"], "type": "arrow"}])
        self.assertEqual(el.bind_end(arrow, "start", a, by_id=by_id), [])         # already listed
        self.assertEqual(len(a["boundElements"]), 1)

    def test_rebinding_and_freeing_clean_the_old_host(self) -> None:
        by_id = self.scene()
        a, b, _c, arrow = self.parts(by_id)
        el.bind_end(arrow, "end", a, by_id=by_id)
        changed = el.bind_end(arrow, "end", b, by_id=by_id)
        self.assertEqual(changed, [a, b])
        self.assertIsNone(a["boundElements"])
        self.assertEqual(arrow["endBinding"]["elementId"], b["id"])
        changed = el.bind_end(arrow, "end", None, by_id=by_id)
        self.assertEqual(changed, [b])
        self.assertIsNone(arrow["endBinding"])
        self.assertIsNone(b["boundElements"])
        with self.assertRaises(ValueError):
            el.bind_end(arrow, "middle", a)

    def test_refit_puts_both_ends_on_the_edges(self) -> None:
        by_id = self.scene()
        a, b, _c, arrow = self.parts(by_id)
        el.bind_end(arrow, "start", a, by_id=by_id)
        el.bind_end(arrow, "end", b, by_id=by_id)
        self.assertTrue(el.refit_arrow(arrow, by_id))
        route = el.route_of(arrow)
        self.assertTrue(close(route[0][0], 100 + el.BIND_GAP) and close(route[0][1], 50))
        self.assertTrue(close(route[1][0], 300 - el.BIND_GAP) and close(route[1][1], 50))
        b["y"] = 200                                                              # b moves down
        el.refit_arrow(arrow, by_id)
        end = el.route_of(arrow)[-1]
        self.assertTrue(end[1] > 100)                                              # follows it
        # free arrow: left alone
        free = el.linear_element("arrow", [(5, 5), (9, 9)], roughness=0)
        self.assertFalse(el.refit_arrow(free, by_id))
        self.assertEqual(el.route_of(free), [(5, 5), (9, 9)])

    def test_detach_a_box_frees_its_arrows_and_takes_its_label(self) -> None:
        by_id = self.scene()
        a, b, _c, arrow = self.parts(by_id)
        label = el.add_label(a, "A", font=el.FONT_HELVETICA, roughness=0)
        by_id[label["id"]] = label
        el.bind_end(arrow, "start", a, by_id=by_id)
        el.bind_end(arrow, "end", b, by_id=by_id)
        gone, changed = el.detach(a, by_id)
        self.assertEqual(gone, [a["id"], label["id"]])
        self.assertIsNone(arrow["startBinding"])
        self.assertIsNotNone(arrow["endBinding"])
        self.assertEqual(changed, [arrow])

    def test_detach_an_arrow_and_a_label_clean_their_hosts(self) -> None:
        by_id = self.scene()
        a, b, _c, arrow = self.parts(by_id)
        label = el.add_label(b, "B", font=el.FONT_HELVETICA, roughness=0)
        by_id[label["id"]] = label
        el.bind_end(arrow, "start", a, by_id=by_id)
        gone, changed = el.detach(arrow, by_id)
        self.assertEqual((gone, changed), ([arrow["id"]], [a]))
        self.assertIsNone(a["boundElements"])
        gone, changed = el.detach(label, by_id)
        self.assertEqual((gone, changed), ([label["id"]], [b]))
        self.assertIsNone(b["boundElements"])


class TestGeometryExtensions(unittest.TestCase):
    def test_wrap_default_is_unchanged(self) -> None:
        self.assertEqual(geometry.wrap("aaa  bbb\nccc", 7, 5), ["aaa bbb", "ccc"])
        self.assertEqual(geometry.wrap("a" * 30, 10, 3), ["a" * 9 + "…"])

    def test_wrap_verbatim(self) -> None:
        self.assertEqual(geometry.wrap("aaa  bbb\n\nccc", 20, math.inf, verbatim=True),
                         ["aaa  bbb", "", "ccc"])
        self.assertEqual(geometry.wrap("x" * 12, 5, math.inf, verbatim=True), ["xxxxx", "xxxxx", "xx"])
        self.assertEqual(geometry.wrap("a\nb\nc\nd", 5, 2, verbatim=True), ["a", "b…"])
        self.assertEqual(geometry.wrap("", 5, math.inf, verbatim=True), [""])

    def test_exit_t_default_is_the_rectangle(self) -> None:
        box = (0, 0, 200, 100)
        self.assertEqual(geometry.exit_t(box, 50, 0), geometry.exit_t(box, 50, 0, "rectangle"))
        self.assertEqual(geometry.exit_t(box, 50, 0, "anything else"), 2.0)
        self.assertEqual(geometry.exit_t(box, 0, 0), math.inf)
        self.assertEqual(geometry.exit_t(box, 0, 0, "ellipse"), math.inf)

    def test_exit_t_for_inscribed_shapes(self) -> None:
        box = (0, 0, 200, 100)
        self.assertTrue(close(geometry.exit_t(box, 100, 0, "ellipse"), 1.0))
        self.assertTrue(close(geometry.exit_t(box, 100, 50, "diamond"), 0.5))
        self.assertTrue(close(geometry.exit_t(box, 100, 50, "ellipse"), 1 / math.sqrt(2)))
        self.assertTrue(close(geometry.exit_t(box, 100, 50), 1.0))
        self.assertEqual(box_of({"x": 0, "y": 0, "width": 200, "height": 100}), box)


if __name__ == "__main__":
    unittest.main()
