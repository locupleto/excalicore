"""The canvas/model bridge: what the model is shown, and what it is allowed
to change."""

from __future__ import annotations

import json
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

    def test_a_stencil_instance_appears_once_with_its_label_and_subject(self):
        out = scene.compact(corpus.elements("stencil-instances"))
        placed = {e["id"]: e for e in out if e.get("type") == "stencil"}
        self.assertEqual(set(placed), {"g-c-itil", "g-c-cmdb"})
        actor = placed["g-c-itil"]
        self.assertEqual(actor["name"], "bastion-actor")
        self.assertEqual(actor["label"], "ITIL Users")
        self.assertEqual(actor["subject"], {"bastion": {"kind": "component", "key": "itil"}})
        self.assertEqual((actor["x"], actor["y"]), (126, 141))
        store = placed["g-c-cmdb"]
        self.assertEqual(store["label"], "CMDB", "a label carried as a property on the body counts")
        ids = {e.get("id") for e in out}
        self.assertNotIn("c-itil", ids, "the parts are folded away")
        self.assertIn("neighbour", ids)
        arrow = next(e for e in out if e.get("type") == "arrow")
        self.assertEqual(arrow["end"], {"id": "c-cmdb"}, "an arrow bound to a body keeps the binding")

    def test_a_stencil_placement_is_a_valid_patch(self):
        prose, patch = scene.extract_patch(corpus.reply("stencil-placement"))
        self.assertEqual(prose, "A data store beside the console.")
        self.assertEqual(patch["elements"][0]["stencil"], "cylinder")
        self.assertEqual(patch["elements"][0]["subject"], {"bastion": {"kind": "datastore"}})
        self.assertIsNone(scene.valid_patch({"elements": [{"stencil": "cylinder", "x": 1}]}),
                          "a placement without both coordinates is no placement")

    def test_the_old_stamp_tags_are_no_longer_read(self):
        els = [{
            "id": "e1", "type": "ellipse", "x": 0, "y": 0, "width": 10, "height": 10,
            "customData": {"stamp": "Operator", "stampGroup": "sg-77"},
        }]
        out = scene.compact(els)
        # an element carrying only the old tags is an ordinary element now,
        # not folded into a stencil instance
        self.assertEqual([e.get("type") for e in out], ["ellipse"])

    def test_an_instance_without_a_frame_falls_back_to_its_footprint(self):
        out = scene.compact(corpus.elements("instance-group"))
        instances = [e for e in out if e.get("type") == "stencil"]
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["id"], "sg-77")
        self.assertEqual(instances[0]["name"], "Operator")
        self.assertNotIn("subject", instances[0])
        # the primitives it is made of are not shown separately
        self.assertNotIn("instance-a1", {e.get("id") for e in out})
        # the group's footprint covers all its members
        self.assertEqual((instances[0]["width"], instances[0]["height"]), (50, 90))

    def test_an_instance_group_does_not_swallow_its_neighbours(self):
        out = scene.compact(corpus.elements("instance-group"))
        self.assertIn("box-next-to-instance", {e.get("id") for e in out})

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

    def test_the_old_stamp_placement_is_refused_like_any_malformed_entry(self):
        # The pre-contract spelling names no type and no "stencil" key, so it
        # falls back to needing a type — and having none, it takes the whole
        # patch down with it, exactly like any other malformed element.
        self.assertIsNone(scene.valid_patch({"elements": [{"stamp": "Operator", "x": 1, "y": 2}]}))

    def test_a_blank_name_is_not_a_placement(self):
        # Whitespace is not a symbol name, so this falls back to needing a
        # type — and having none, it takes the whole patch down with it.
        self.assertIsNone(scene.valid_patch({"elements": [{"stencil": "   ", "x": 1, "y": 2}]}))

    def test_a_placement_obeys_the_same_bounds_as_anything_else(self):
        far = {"stencil": "Operator", "x": scene.MAX_COORD + 1, "y": 0}
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

    def test_a_stamp_placement_is_no_longer_read(self):
        message = corpus.reply("stamp-placement")
        prose, patch = scene.extract_patch(message)
        self.assertIsNone(patch)
        self.assertEqual(prose, message.strip())


def _scene_fixture(name):
    return json.loads((corpus.ROOT / "scene" / f"{name}.json").read_text())


def _json_plain(value):
    return json.loads(json.dumps(value))


def _scene_kwargs(options):
    out = {}
    for key, value in (options or {}).items():
        if key == "keep":
            out["keep"] = tuple(value)
        elif key == "opaque":
            out["opaque"] = frozenset(value)
        elif key == "maxPoints":
            out["max_points"] = value
        elif key == "maxCoord":
            out["max_coord"] = value
    return out


class TestSceneFixtures(unittest.TestCase):
    """corpus/scene/*.json were generated by python/tools/gen_corpus_scene.py;
    the TypeScript half replays them too. Python must still reproduce every
    case, or one of the two has drifted from the fixtures."""

    def _elements(self, case):
        return corpus.elements(case["scene"]) if "scene" in case else case["elements"]

    def _run(self, case):
        fn, kw = case["fn"], _scene_kwargs(case.get("options"))
        if fn == "compact":
            return scene.compact(self._elements(case), **kw)
        if fn == "rdp":
            points = corpus.elements(case["scene"])[case["index"]]["points"] if "scene" in case else case["points"]
            return scene.rdp(points, case["eps"])
        if fn == "strokeSummary":
            element = corpus.elements(case["scene"])[case["index"]] if "scene" in case else case["element"]
            return scene.stroke_summary(element, **kw)
        if fn == "instanceOf":
            return scene.instance_of(case["element"])
        if fn == "stencilSummary":
            members = (
                [e for e in corpus.elements(case["scene"]) if scene.instance_of(e) == case["instance"]]
                if "scene" in case else case["members"]
            )
            return scene.stencil_summary(case["instance"], members)
        if fn == "bbox":
            return scene.bbox(self._elements(case))
        if fn == "saneGeometry":
            return scene.sane_geometry(case["element"], **kw)
        if fn == "validPatch":
            return scene.valid_patch(case["obj"], **kw)
        if fn == "extractPatch":
            message = corpus.reply(case["reply"]) if "reply" in case else case["message"]
            prose, patch = scene.extract_patch(message, **kw)
            return {"prose": prose, "patch": patch}
        self.fail(f"unknown fn {fn}")

    def test_python_reproduces_every_case(self):
        total = 0
        for name in ("compact", "strokes", "stencils", "patch"):
            fixture = _scene_fixture(name)
            self.assertTrue(fixture["doc"])
            for case in fixture["cases"]:
                with self.subTest(file=name, case=case["name"]):
                    self.assertEqual(_json_plain(self._run(case)), case["expect"])
                total += 1
        self.assertGreater(total, 0)

    def test_every_corpus_scene_and_reply_has_a_case(self):
        compacts = {c["scene"] for c in _scene_fixture("compact")["cases"] if "scene" in c}
        replies = {c["reply"] for c in _scene_fixture("patch")["cases"] if "reply" in c}
        self.assertEqual(compacts, set(corpus.scene_names()))
        self.assertEqual(replies, {p.stem for p in corpus.REPLIES.glob("*.txt")})


if __name__ == "__main__":
    unittest.main()
