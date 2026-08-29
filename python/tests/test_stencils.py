"""The stencil contract, server side, against the same corpus as the TypeScript half."""

from __future__ import annotations

import json
import unittest

from excalicore import stencils

from . import corpus

STENCILS = corpus.ROOT / "stencils"


def fixture(name: str) -> dict:
    return json.loads((STENCILS / f"{name}.json").read_text())


class TestValidate(unittest.TestCase):
    def test_every_corpus_stencil_is_valid(self):
        for path in sorted(STENCILS.glob("*.json")):
            if path.stem == "rejected":
                continue
            fx = json.loads(path.read_text())
            if "item" in fx:
                s = stencils.from_library_item(fx["item"], fx["roles"])
            else:
                s = fx
            self.assertEqual(stencils.validate(s["elements"]), [], path.stem)

    def test_every_rejected_case_is_rejected_with_a_sentence(self):
        cases = fixture("rejected")["cases"]
        self.assertGreaterEqual(len(cases), 6)
        for case in cases:
            errors = stencils.validate(case["elements"])
            self.assertTrue(errors, f'"{case["reason"]}" was accepted')
            for e in errors:
                self.assertTrue(e.endswith("."), e)

    def test_the_body_must_be_bindable(self):
        for kind in ("line", "arrow", "freedraw", "text"):
            errors = stencils.validate([{
                "type": kind, "id": "a", "x": 0, "y": 0, "width": 10, "height": 10,
                "customData": {"stencil": {"role": "body", "frame": {"dx": 0, "dy": 0, "sw": 1, "sh": 1}}},
            }])
            self.assertTrue(any("cannot be bound to" in e for e in errors), kind)


class TestFromLibraryItem(unittest.TestCase):
    def test_default_roles_picks_the_largest_bindable_shape(self):
        for name in ("armory-server", "armory-stick-man"):
            fx = fixture(name)
            self.assertEqual(stencils.default_roles(fx["item"]), fx["roles"], name)
        self.assertEqual(stencils.default_roles({"elements": [
            {"id": "a", "type": "line", "x": 0, "y": 0, "width": 9, "height": 0}]}), {})

    def test_a_marked_role_wins_over_the_heuristic(self):
        item = {"name": "two", "elements": [
            {"id": "big", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100},
            {"id": "small", "type": "ellipse", "x": 0, "y": 0, "width": 10, "height": 10,
             "customData": {"stencil": {"role": "body"}}},
        ]}
        self.assertEqual(stencils.default_roles(item), {"small": {"role": "body"}})

    def test_the_frame_and_anchors_are_derived_the_way_the_typescript_half_derives_them(self):
        fx = fixture("armory-stick-man")
        s = stencils.from_library_item(fx["item"], fx["roles"])
        head = next(e for e in s["elements"] if e["customData"]["stencil"]["role"] == "body")
        self.assertEqual(head["type"], "ellipse")
        box = stencils.subject_box(s["elements"])
        xs = [e["x"] for e in s["elements"]]
        self.assertAlmostEqual(box[0], min(xs))
        self.assertAlmostEqual(box[1], head["y"])
        self.assertGreater(box[3], head["height"] * 2, "the figure is taller than its head")
        for el in s["elements"]:
            tag = el["customData"]["stencil"]
            if tag["role"] == "body":
                continue
            self.assertEqual(tag["role"], "decoration")
            self.assertEqual(tag["size"], "fit")
            self.assertEqual(tag["offset"], {"dx": 0, "dy": 0})
            self.assertIn("anchor", tag)
        self.assertEqual(head["version"], fx["item"]["elements"][0]["version"], "everything else is verbatim")

    def test_an_item_with_nothing_bindable_is_refused_with_a_sentence(self):
        fx = fixture("armory-server")
        with self.assertRaises(stencils.StencilError) as ctx:
            stencils.from_library_item(fx["item"], {})
        self.assertTrue(any('exactly one element with role "body"' in e for e in ctx.exception.errors))

    def test_a_placed_instance_gives_its_subject_box_back(self):
        parts = [e for e in corpus.elements("stencil-instances")
                 if (e.get("customData") or {}).get("stencil", {}).get("instance") == "g-c-cmdb"]
        self.assertEqual(stencils.subject_box(parts), (502.0, 202.0, 200.0, 76.0))
