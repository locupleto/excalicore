"""The canvas/model bridge: what the model is shown, and what it is allowed
to change."""

from __future__ import annotations

import math
import unittest

from excalicore import scene

from . import corpus


class TestCompact(unittest.TestCase):
    def test_bound_text_folds_into_its_container(self):
        out = scene.compact(corpus.elements("bound-labels"))
        labelled = [e for e in out if "label" in e]
        self.assertTrue(labelled)
        for element in out:
            self.assertNotIn("containerId", element)
        # every folded label is gone as a standalone element
        ids = {e.get("id") for e in out}
        for element in corpus.elements("bound-labels"):
            if element.get("type") == "text" and element.get("containerId"):
                self.assertNotIn(element["id"], ids)

    def test_bound_arrows_become_id_refs_without_points(self):
        raw = corpus.elements("arrow-bindings")
        on_board = {e["id"] for e in raw}
        bound = {
            e["id"] for e in raw
            if e.get("type") == "arrow"
            and (e.get("startBinding") or {}).get("elementId") in on_board
        }
        self.assertTrue(bound)
        for element in scene.compact(raw):
            if element.get("id") in bound:
                self.assertIn("start", element)
                self.assertNotIn("points", element)

    def test_a_binding_to_a_missing_element_is_not_offered_as_a_ref(self):
        # A dangling binding would send the model chasing an id that is not on
        # the board; it keeps its own points instead.
        out = {e["id"]: e for e in scene.compact(corpus.elements("arrow-bindings"))}
        self.assertNotIn("start", out["arrow-2"])
        self.assertIn("points", out["arrow-2"])

    def test_only_kept_fields_survive(self):
        allowed = set(scene.KEEP) | {"name", "closed"}
        for element in scene.compact(corpus.elements("bound-labels")):
            self.assertLessEqual(set(element) - allowed, set())

    def test_a_stroke_is_summarized_within_the_point_budget(self):
        raw = corpus.elements("freedraw")
        self.assertGreater(len(raw[0]["points"]), scene.MAX_STROKE_POINTS)
        out = scene.compact(raw)
        self.assertEqual(len(out), 1)
        self.assertLessEqual(len(out[0]["points"]), scene.MAX_STROKE_POINTS)
        self.assertNotIn("pressures", out[0])

    def test_a_stroke_summary_is_in_absolute_board_coordinates(self):
        raw = corpus.elements("freedraw")[0]
        summary = scene.stroke_summary(raw)
        first = summary["points"][0]
        self.assertAlmostEqual(first[0], round(raw["x"] + raw["points"][0][0]), delta=1)

    def test_a_stamp_group_appears_once(self):
        out = scene.compact(corpus.elements("stamp-group"))
        stamps = [e for e in out if e.get("type") == "stamp"]
        self.assertEqual(len(stamps), 1)
        self.assertEqual(stamps[0]["id"], "sg-77")
        self.assertEqual(stamps[0]["name"], "Operator")
        # the primitives it is made of are not shown separately
        self.assertNotIn("stamp-a1", {e.get("id") for e in out})
        # the group's footprint covers all its members
        self.assertEqual((stamps[0]["width"], stamps[0]["height"]), (50, 90))

    def test_a_stamp_group_does_not_swallow_its_neighbours(self):
        out = scene.compact(corpus.elements("stamp-group"))
        self.assertIn("box-next-to-stamp", {e.get("id") for e in out})

    def test_an_image_is_geometry_only(self):
        out = scene.compact(corpus.elements("image-and-files"))
        self.assertEqual(len(out), 1)          # the deleted one is not shown
        self.assertEqual(set(out[0]), {"id", "type", "x", "y", "width", "height"})
        self.assertNotIn("fileId", out[0])

    def test_deleted_elements_are_not_shown(self):
        out = scene.compact(corpus.elements("image-and-files"))
        self.assertNotIn("img-02", {e.get("id") for e in out})

    def test_an_empty_canvas_compacts_to_nothing(self):
        self.assertEqual(scene.compact(None), [])
        self.assertEqual(scene.compact([]), [])


class TestRdp(unittest.TestCase):
    def test_endpoints_are_always_kept(self):
        points = [[float(i), float(i % 3)] for i in range(50)]
        out = scene.rdp(points, 0.5)
        self.assertEqual(out[0], points[0])
        self.assertEqual(out[-1], points[-1])

    def test_a_coarser_tolerance_never_keeps_more_points(self):
        points = corpus.elements("freedraw")[0]["points"]
        counts = [len(scene.rdp(points, eps)) for eps in (0.5, 1, 2, 4, 8, 16)]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_a_straight_line_collapses_to_its_ends(self):
        points = [[float(i), 0.0] for i in range(20)]
        self.assertEqual(scene.rdp(points, 0.1), [[0.0, 0.0], [19.0, 0.0]])

    def test_short_polylines_pass_through(self):
        self.assertEqual(scene.rdp([[0, 0], [1, 1]], 99), [[0, 0], [1, 1]])


class TestSanity(unittest.TestCase):
    def test_absent_coordinates_are_fine(self):
        self.assertTrue(scene.sane_geometry({"type": "rectangle"}))

    def test_a_boolean_is_not_a_coordinate(self):
        self.assertFalse(scene.sane_geometry({"x": True}))

    def test_infinities_and_nans_are_rejected(self):
        self.assertFalse(scene.sane_geometry({"x": math.inf}))
        self.assertFalse(scene.sane_geometry({"y": math.nan}))

    def test_far_away_is_a_hallucination(self):
        self.assertFalse(scene.sane_geometry({"x": scene.MAX_COORD + 1}))
        self.assertTrue(scene.sane_geometry({"x": scene.MAX_COORD}))


class TestPatchValidation(unittest.TestCase):
    def test_one_bad_element_rejects_the_whole_patch(self):
        _, patch = scene.extract_patch(corpus.reply("malformed-geometry"))
        self.assertIsNone(patch)

    def test_an_echoed_stroke_is_dropped_but_the_rest_stands(self):
        _, patch = scene.extract_patch(corpus.reply("echoes-opaque"))
        self.assertIsNotNone(patch)
        self.assertEqual([e["id"] for e in patch["elements"]], ["frame-1"])

    def test_a_patch_saying_nothing_is_not_a_patch(self):
        self.assertIsNone(scene.valid_patch({"elements": [], "delete": []}))
        self.assertIsNone(scene.valid_patch({}))
        self.assertIsNone(scene.valid_patch("not a dict"))

    def test_a_deletion_alone_is_a_patch(self):
        patch = scene.valid_patch({"delete": ["n7"]})
        self.assertEqual(patch, {"elements": [], "delete": ["n7"]})

    def test_an_element_needs_a_type(self):
        self.assertIsNone(scene.valid_patch({"elements": [{"x": 1, "y": 2}]}))

    def test_a_stamp_placement_needs_a_position_not_a_type(self):
        self.assertIsNotNone(scene.valid_patch({"elements": [{"stamp": "Operator", "x": 1, "y": 2}]}))
        self.assertIsNone(scene.valid_patch({"elements": [{"stamp": "Operator", "x": 1}]}))

    def test_a_blank_name_is_not_a_placement(self):
        # Whitespace is not a symbol name, so this falls back to needing a
        # type — and having none, it takes the whole patch down with it.
        self.assertIsNone(scene.valid_patch({"elements": [{"stamp": "   ", "x": 1, "y": 2}]}))

    def test_a_placement_obeys_the_same_bounds_as_anything_else(self):
        far = {"stamp": "Operator", "x": scene.MAX_COORD + 1, "y": 0}
        self.assertIsNone(scene.valid_patch({"elements": [far]}))

    def test_non_string_delete_ids_are_discarded(self):
        patch = scene.valid_patch({"delete": ["a", 7, None, "b"]})
        self.assertEqual(patch["delete"], ["a", "b"])


class TestExtraction(unittest.TestCase):
    def test_a_fenced_patch_is_lifted_and_the_prose_left_clean(self):
        prose, patch = scene.extract_patch(corpus.reply("fenced-patch"))
        self.assertEqual(prose, "Two boxes and an arrow between them, then.")
        self.assertEqual(len(patch["elements"]), 3)

    def test_an_unfenced_patch_works_too(self):
        prose, patch = scene.extract_patch(corpus.reply("bare-patch"))
        self.assertEqual(prose, "Dropping the stale node.")
        self.assertEqual(patch["delete"], ["n7"])

    def test_the_last_patch_wins(self):
        _, patch = scene.extract_patch(corpus.reply("two-patches-last-wins"))
        self.assertEqual([e["id"] for e in patch["elements"]], ["b"])

    def test_prose_without_a_patch_is_all_prose(self):
        prose, patch = scene.extract_patch(corpus.reply("prose-only"))
        self.assertIsNone(patch)
        self.assertTrue(prose.startswith("I would leave the board"))

    def test_a_rejected_patch_leaves_the_message_whole(self):
        message = corpus.reply("malformed-geometry")
        prose, patch = scene.extract_patch(message)
        self.assertIsNone(patch)
        self.assertEqual(prose, message.strip())

    def test_a_stamp_placement_survives_extraction(self):
        _, patch = scene.extract_patch(corpus.reply("stamp-placement"))
        self.assertEqual(patch["elements"][0]["stamp"], "Operator")


if __name__ == "__main__":
    unittest.main()
