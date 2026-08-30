"""The geometry module, against the corpus.

Each ``corpus/geometry/*.json`` file holds a ``{doc, cases}`` object; every
case names the function it exercises (``fn``) so one loop per file can
dispatch to the right call — the same shape ``typescript/tests/geometry.test.ts``
reads. Floats are compared with a tolerance, matching the TypeScript side's
1e-6 and ``unittest``'s own ``assertAlmostEqual(places=6)`` default.
"""

from __future__ import annotations

import math
import unittest
from typing import Any

from excalicore import geometry

from . import corpus

EPS = 1e-6


def close(case: unittest.TestCase, actual: Any, expected: Any, what: str) -> None:
    """Deep, tolerant equality: numbers within EPS, everything else exact.
    Used throughout because the corpus mixes floats (a trimmed segment) with
    exact values (an id, a side word, a boolean) in the same object."""
    if expected is None:
        case.assertIsNone(actual, what)
        return
    if isinstance(expected, bool):
        case.assertEqual(actual, expected, what)
        return
    if isinstance(expected, (int, float)):
        case.assertTrue(
            isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and math.isfinite(actual) and abs(actual - expected) < EPS,
            f"{what}: {actual} != {expected}",
        )
        return
    if isinstance(expected, (list, tuple)):
        case.assertTrue(isinstance(actual, (list, tuple)), f"{what}: expected a sequence, got {actual!r}")
        case.assertEqual(len(actual), len(expected), f"{what}: length")
        for i, e in enumerate(expected):
            close(case, actual[i], e, f"{what}[{i}]")
        return
    if isinstance(expected, dict):
        # A box comes back from this module as an (x, y, width, height)
        # TUPLE (the form stencils.py already used); the corpus, shared with
        # the TypeScript half, spells a box as a dict. Read the tuple back
        # through the same four field names before comparing.
        if isinstance(actual, tuple) and set(expected) <= {"x", "y", "width", "height"} and len(actual) == 4:
            actual = dict(zip(("x", "y", "width", "height"), actual))
        case.assertTrue(isinstance(actual, dict), f"{what}: expected a dict, got {actual!r}")
        for k, v in expected.items():
            case.assertIn(k, actual, f"{what}.{k} missing")
            close(case, actual[k], v, f"{what}.{k}")
        return
    case.assertEqual(actual, expected, what)


def cases(name: str) -> dict[str, Any]:
    fx = corpus.geometry_fixture(name)
    assert fx["doc"], f"{name}.json needs a doc string"
    assert fx["cases"], f"{name}.json has no cases"
    return fx


class TestBoxes(unittest.TestCase):
    def test_boxes_json(self):
        fx = cases("boxes")
        seen: set[str] = set()
        for c in fx["cases"]:
            seen.add(c["fn"])
            what = f'{c["fn"]}: {c["name"]}'
            if c["fn"] == "boxOf":
                close(self, geometry.box_of(c["element"]), c["expect"], what)
            elif c["fn"] == "union":
                close(self, geometry.union(c["boxes"]), c["expect"], what)
            elif c["fn"] == "contains":
                self.assertEqual(geometry.contains(c["box"], c["point"]), c["expect"], what)
            elif c["fn"] == "overlap":
                self.assertEqual(geometry.overlap(c["a"], c["b"]), c["expect"], what)
            elif c["fn"] == "centre":
                close(self, geometry.centre(c["box"]), c["expect"], what)
            elif c["fn"] == "area":
                close(self, geometry.area(c["box"]), c["expect"], what)
            else:
                self.fail(f'unknown fn {c["fn"]} in boxes.json')
        self.assertEqual(seen, {"boxOf", "union", "contains", "overlap", "centre", "area"})


class TestFaces(unittest.TestCase):
    def test_faces_json(self):
        fx = cases("faces")
        seen: set[str] = set()
        for c in fx["cases"]:
            seen.add(c["fn"])
            what = f'{c["fn"]}: {c["name"]}'
            if c["fn"] == "facingSides":
                self.assertEqual(list(geometry.facing_sides(c["a"], c["b"])), c["expect"], what)
            elif c["fn"] == "pointOnSide":
                close(self, geometry.point_on_side(c["box"], c["side"], c["t"]), c["expect"], what)
            elif c["fn"] == "along":
                close(self, geometry.along(c["other"], c["side"]), c["expect"], what)
            elif c["fn"] == "anchorUV":
                close(self, geometry.anchor_uv(c["point"], c["box"]), c["expect"], what)
            elif c["fn"] == "anchorXY":
                close(self, geometry.anchor_xy(c["uv"], c["box"]), c["expect"], what)
            elif c["fn"] == "exitT":
                close(self, geometry.exit_t(c["box"], c["dx"], c["dy"]), c["expect"], what)
            elif c["fn"] == "centreSegment":
                close(self, geometry.centre_segment(c["a"], c["b"], c["gap"]), c["expect"], what)
            else:
                self.fail(f'unknown fn {c["fn"]} in faces.json')
        self.assertEqual(
            seen,
            {"facingSides", "pointOnSide", "along", "anchorUV", "anchorXY", "exitT", "centreSegment"},
        )

    def test_anchor_uv_xy_round_trip_on_every_anchor_case(self):
        fx = cases("faces")
        for c in fx["cases"]:
            if c["fn"] != "anchorUV":
                continue
            uv = geometry.anchor_uv(c["point"], c["box"])
            back = geometry.anchor_xy(uv, c["box"])
            close(self, back, c["point"], f'round trip: {c["name"]}')


class TestBends(unittest.TestCase):
    def test_bends_json(self):
        fx = cases("bends")
        seen: set[str] = set()
        for c in fx["cases"]:
            seen.add(c["fn"])
            what = f'{c["fn"]}: {c["name"]}'
            if c["fn"] == "relativeBends":
                close(self, geometry.relative_bends(c["points"]), c["expect"], what)
            elif c["fn"] == "absoluteRoute":
                close(self, geometry.absolute_route(c["bends"], c["a"], c["b"]), c["expect"], what)
            else:
                self.fail(f'unknown fn {c["fn"]} in bends.json')
        self.assertEqual(seen, {"relativeBends", "absoluteRoute"})

    def test_a_right_angle_survives_relative_bends_absolute_route_translated(self):
        # The property the corpus fixes numerically, stated directly:
        # bending an arrow, moving both its boxes by the same vector, and
        # refitting produces the same shape translated, not sheared.
        a = (100.0, 100.0)
        b = (400.0, 100.0)
        elbow = [a, (100.0, 300.0), b]
        bends = geometry.relative_bends(elbow)
        shift = (77.0, -33.0)
        a2 = (a[0] + shift[0], a[1] + shift[1])
        b2 = (b[0] + shift[0], b[1] + shift[1])
        route = geometry.absolute_route(bends, a2, b2)
        self.assertEqual(len(route), 3)
        close(self, route[0], a2, "start")
        close(self, route[2], b2, "end")
        close(self, route[1], (elbow[1][0] + shift[0], elbow[1][1] + shift[1]), "knee")


class TestArrows(unittest.TestCase):
    def test_arrows_json(self):
        fx = cases("arrows")
        seen: set[str] = set()
        for c in fx["cases"]:
            seen.add(c["fn"])
            what = f'{c["fn"]}: {c["name"]}'
            if c["fn"] == "arrowKind":
                self.assertEqual(geometry.arrow_kind(c["element"]), c["expect"], what)
            elif c["fn"] == "arrowFields":
                # Exact, not tolerant: arrowFields is a small discrete dict,
                # and the whole point is whether "elbowed" is even PRESENT.
                self.assertEqual(geometry.arrow_fields(c["kind"]), c["expect"], what)
            elif c["fn"] == "arrowElement":
                close(self, geometry.arrow_element(c["points"]), c["expect"], what)
            else:
                self.fail(f'unknown fn {c["fn"]} in arrows.json')
        self.assertEqual(seen, {"arrowKind", "arrowFields", "arrowElement"})


class TestWrap(unittest.TestCase):
    def test_wrap_json(self):
        fx = cases("wrap")
        seen: set[str] = set()
        for c in fx["cases"]:
            seen.add(c["fn"])
            what = f'{c["fn"]}: {c["name"]}'
            if c["fn"] == "wrap":
                self.assertEqual(geometry.wrap(c["text"], c["cols"], c["maxLines"]), c["expect"], what)
            elif c["fn"] == "ellipsise":
                self.assertEqual(geometry.ellipsise(c["line"], c["cols"]), c["expect"], what)
            elif c["fn"] == "terse":
                self.assertEqual(geometry.terse(c["text"], c["maxWords"]), c["expect"], what)
            elif c["fn"] == "lineCount":
                self.assertEqual(geometry.line_count(c["text"], c["cols"]), c["expect"], what)
            else:
                self.fail(f'unknown fn {c["fn"]} in wrap.json')
        self.assertEqual(seen, {"wrap", "ellipsise", "terse", "lineCount"})

    def test_line_count_is_exactly_wrap_uncapped_length(self):
        for text, cols in (
            ("a modest label", 22),
            ("", 10),
            ("supercalifragilisticexpialidocious", 12),
        ):
            self.assertEqual(
                geometry.line_count(text, cols),
                len(geometry.wrap(text, cols, math.inf)),
                text,
            )


class TestSkeletonPipeline(unittest.TestCase):
    """normalizeBoundArrows and topAlignCrowdedLabels are TypeScript only —
    the pass a sketch application runs in the browser between a model's
    reply and convertToExcalidrawElements. No server has a use for them, so
    there is no Python twin; these are marked skipped with the reason, the
    way test_parity.py's cases are skipped when no source is configured."""

    def test_routes_json(self):
        self.skipTest(
            "normalizeBoundArrows is browser-side pass; TypeScript only — see Geometry-Module"
        )

    def test_crowding_json(self):
        self.skipTest(
            "topAlignCrowdedLabels is browser-side pass; TypeScript only — see Geometry-Module"
        )


if __name__ == "__main__":
    unittest.main()
