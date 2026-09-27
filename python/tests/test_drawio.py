"""The draw.io builder: containment, attachment, and the two files.

Structural checks only; whether draw.io itself accepts the output was checked
by exporting through the draw.io desktop CLI (``drawio -x -f png``), which
renders the ``.drawio`` and the ``.drawio.svg`` identically.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from excalicore import drawio

SVG = "{http://www.w3.org/2000/svg}"


def board() -> drawio.Diagram:
    """An outer region holding an inner one; a box in each; one arrow with a
    bend and one straight."""
    d = drawio.Diagram("Board & <co>")
    d.container("inner", "Inner", (120, 140, 400, 200), parent="outer",
                style={"rounded": "1", "fillColor": "#eeeeee"})
    d.container("outer", "Outer", (100, 100, 700, 400))
    d.vertex("a", ["A box", "its tech"], (150, 200, 120, 60), parent="inner")
    d.vertex("db", ["Store"], (600, 200, 120, 60), shape="cylinder", parent="outer")
    d.vertex("who", ["Someone"], (0, 0, 60, 60), shape="actor")
    d.edge("ab", "a", "db", [(270, 230), (400, 230), (400, 220), (600, 220)],
           ["reads"], style={"strokeColor": "#123456"})
    d.edge("wa", "who", "a", [(30, 60), (180, 200)])
    return d


def cells(tree: ET.Element) -> dict[str, ET.Element]:
    return {c.get("id"): c for c in tree.iter("mxCell")}


def style(cell: ET.Element) -> dict[str, str]:
    parts = [p for p in cell.get("style", "").strip(";").split(";") if p]
    return dict(p.split("=", 1) for p in parts)


def geo(cell: ET.Element) -> tuple[float, ...]:
    g = cell.find("mxGeometry")
    return tuple(float(g.get(k)) for k in ("x", "y", "width", "height"))


class TestTheFile(unittest.TestCase):
    def test_an_uncompressed_mxfile_with_the_two_root_cells(self) -> None:
        tree = ET.fromstring(board().to_drawio())
        self.assertEqual(tree.tag, "mxfile")
        self.assertEqual(tree.find("diagram").get("name"), "Board & <co>")
        ids = [c.get("id") for c in tree.iter("mxCell")]
        self.assertEqual(ids[:2], ["0", "1"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_parent_is_written_before_anything_inside_it(self) -> None:
        order = [c.get("id") for c in board().to_mxfile().iter("mxCell")]
        for cell in board().to_mxfile().iter("mxCell"):
            parent = cell.get("parent")
            if parent:
                self.assertLess(order.index(parent), order.index(cell.get("id")))
        self.assertEqual(order[-2:], ["ab", "wa"])

    def test_a_duplicate_id_is_refused(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", [], (0, 0, 1, 1))
        with self.assertRaises(ValueError):
            d.vertex("a", [], (0, 0, 1, 1))

    def test_a_parent_that_is_not_a_container_is_refused(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", [], (0, 0, 1, 1))
        d.vertex("b", [], (0, 0, 1, 1), parent="a")
        with self.assertRaises(ValueError):
            d.to_mxfile()

    def test_a_containment_cycle_is_refused(self) -> None:
        d = drawio.Diagram("x")
        d.container("p", "", (0, 0, 1, 1), parent="q")
        d.container("q", "", (0, 0, 1, 1), parent="p")
        with self.assertRaises(ValueError):
            d.to_mxfile()

    def test_an_edge_to_nothing_is_refused(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", [], (0, 0, 1, 1))
        d.edge("e", "a", "ghost", [(0, 0), (1, 1)])
        with self.assertRaises(ValueError):
            d.to_mxfile()

    def test_an_edge_needs_two_points(self) -> None:
        with self.assertRaises(ValueError):
            drawio.Diagram("x").edge("e", "a", "b", [(0, 0)])

    def test_an_unknown_shape_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            drawio.Diagram("x").vertex("a", [], (0, 0, 1, 1), shape="hexagon")


class TestContainment(unittest.TestCase):
    def test_a_child_is_stored_relative_to_its_parent(self) -> None:
        found = cells(board().to_mxfile())
        self.assertEqual(found["inner"].get("parent"), "outer")
        self.assertEqual(geo(found["inner"]), (20.0, 40.0, 400.0, 200.0))
        self.assertEqual(found["a"].get("parent"), "inner")
        self.assertEqual(geo(found["a"]), (30.0, 60.0, 120.0, 60.0))

    def test_a_cell_without_a_parent_sits_on_the_root_layer(self) -> None:
        found = cells(board().to_mxfile())
        self.assertEqual(found["outer"].get("parent"), "1")
        self.assertEqual(geo(found["who"]), (0.0, 0.0, 60.0, 60.0))

    def test_a_container_is_a_container(self) -> None:
        s = style(cells(board().to_mxfile())["inner"])
        self.assertEqual(s["container"], "1")
        self.assertEqual(s["collapsible"], "0")
        self.assertEqual(s["fillColor"], "#eeeeee")


class TestShapes(unittest.TestCase):
    def test_the_shape_is_the_leading_token(self) -> None:
        found = cells(board().to_mxfile())
        self.assertTrue(found["db"].get("style").startswith("shape=cylinder3;"))
        self.assertTrue(found["who"].get("style").startswith("shape=umlActor;"))
        self.assertFalse(found["a"].get("style").startswith("shape="))

    def test_the_callers_style_wins_over_the_structural_default(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", [], (0, 0, 1, 1), shape="actor",
                 style={"verticalLabelPosition": "top"})
        s = style(cells(d.to_mxfile())["a"])
        self.assertEqual(s["verticalLabelPosition"], "top")

    def test_the_font_family_is_the_diagrams_unless_a_cell_says_otherwise(self) -> None:
        d = drawio.Diagram("x", font_family="Inter")
        d.vertex("a", [], (0, 0, 1, 1))
        d.vertex("b", [], (0, 0, 1, 1), style={"fontFamily": "Mono"})
        found = cells(d.to_mxfile())
        self.assertEqual(style(found["a"])["fontFamily"], "Inter")
        self.assertEqual(style(found["b"])["fontFamily"], "Mono")

    def test_lines_are_escaped_html_joined_with_br(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", ["A <b> & co", "tech"], (0, 0, 1, 1))
        self.assertEqual(
            cells(d.to_mxfile())["a"].get("value"), "A &lt;b&gt; &amp; co<br>tech"
        )


class TestEdges(unittest.TestCase):
    def test_an_edge_is_attached_at_both_ends(self) -> None:
        e = cells(board().to_mxfile())["ab"]
        self.assertEqual((e.get("source"), e.get("target")), ("a", "db"))
        self.assertEqual(e.get("parent"), "1")
        self.assertEqual(e.get("edge"), "1")

    def test_the_ends_are_pinned_where_they_meet_the_boxes(self) -> None:
        s = style(cells(board().to_mxfile())["ab"])
        # (270, 230) on a (150, 200, 120, 60) box: the right face, halfway down.
        self.assertEqual((s["exitX"], s["exitY"]), ("1.0", "0.5"))
        # (600, 220) on a (600, 200, 120, 60) box: the left face, a third down.
        self.assertEqual((s["entryX"], s["entryY"]), ("0.0", "0.3333"))
        self.assertEqual((s["exitPerimeter"], s["entryPerimeter"]), ("0", "0"))

    def test_the_points_between_the_ends_become_waypoints(self) -> None:
        g = cells(board().to_mxfile())["ab"].find("mxGeometry")
        self.assertEqual(
            [(p.get("x"), p.get("y")) for p in g.find("Array")],
            [("400", "230"), ("400", "220")],
        )
        self.assertEqual(g.find("mxPoint[@as='sourcePoint']").get("x"), "270")

    def test_a_straight_edge_has_no_waypoints(self) -> None:
        self.assertIsNone(cells(board().to_mxfile())["wa"].find("mxGeometry/Array"))


class TestTheSvg(unittest.TestCase):
    def test_the_svg_carries_the_same_mxfile_in_content(self) -> None:
        d = board()
        svg = ET.fromstring(d.to_svg())
        self.assertEqual(svg.tag, f"{SVG}svg")
        self.assertEqual(
            ET.tostring(ET.fromstring(svg.get("content"))), ET.tostring(d.to_mxfile())
        )

    def test_every_edge_is_a_polyline_with_an_arrowhead_in_its_colour(self) -> None:
        svg = ET.fromstring(board().to_svg())
        lines = svg.findall(f"{SVG}polyline")
        self.assertEqual(len(lines), 2)
        markers = {m.get("id"): m.find(f"{SVG}path").get("fill")
                   for m in svg.iter(f"{SVG}marker")}
        first = lines[0].get("marker-end")[5:-1]
        self.assertEqual(markers[first], "#123456")

    def test_the_text_is_drawn(self) -> None:
        spans = [t.text for t in ET.fromstring(board().to_svg()).iter(f"{SVG}tspan")]
        for text in ("Outer", "Inner", "A box", "its tech", "Store", "Someone", "reads"):
            self.assertIn(text, spans)

    def test_a_long_line_is_wrapped_to_its_box(self) -> None:
        d = drawio.Diagram("x")
        d.vertex("a", ["one two three four five six seven eight nine ten"],
                 (0, 0, 100, 80), style={"fontSize": "14"})
        spans = [t.text for t in ET.fromstring(d.to_svg()).iter(f"{SVG}tspan")]
        self.assertGreater(len(spans), 1)
        self.assertTrue(all(len(s) <= 12 for s in spans), spans)

    def test_the_viewbox_encloses_every_cell(self) -> None:
        d = board()
        x, y, w, h = map(float, ET.fromstring(d.to_svg()).get("viewBox").split())
        bx, by, bw, bh = d.bounds()
        self.assertLessEqual((x, y), (bx, by))
        self.assertGreaterEqual(x + w, bx + bw)
        self.assertGreaterEqual(y + h, by + bh)


if __name__ == "__main__":
    unittest.main()
