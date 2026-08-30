"""The round trip has to be exact, or the canvas breaks without saying so."""

from __future__ import annotations

import json
import unittest

from excalicore import fidelity

from . import corpus


class TestRoundTrip(unittest.TestCase):
    def test_every_corpus_scene_survives_exactly(self):
        for name in corpus.scene_names():
            with self.subTest(scene=name):
                original = corpus.elements(name)
                back = fidelity.reassemble(fidelity.explode(original))
                self.assertEqual(back, original)

    def test_bookkeeping_fields_survive(self):
        original = corpus.elements("bound-labels")
        back = fidelity.reassemble(fidelity.explode(original))
        for was, now in zip(original, back):
            for key in fidelity.BOOKKEEPING:
                if key in was:
                    self.assertEqual(now.get(key), was[key], f"{key} on {was.get('id')}")

    def test_paint_order_is_preserved_when_rows_come_back_shuffled(self):
        original = corpus.elements("instance-group")
        rows = fidelity.explode(original)
        back = fidelity.reassemble(list(reversed(rows)))
        self.assertEqual([e["id"] for e in back], [e["id"] for e in original])

    def test_an_absent_key_is_not_invented(self):
        rows = fidelity.explode([{"id": "a", "type": "rectangle", "x": 1, "y": 2}])
        back = fidelity.reassemble(rows)
        self.assertNotIn("angle", back[0])
        self.assertNotIn("width", back[0])

    def test_a_null_valued_key_stays_null_rather_than_vanishing(self):
        rows = fidelity.explode([{"id": "a", "type": "line", "x": None, "y": None}])
        back = fidelity.reassemble(rows)
        self.assertIn("x", back[0])
        self.assertIsNone(back[0]["x"])

    def test_an_unknown_future_field_is_carried_through(self):
        element = {"id": "a", "type": "rectangle", "someFieldFrom2027": {"deep": [1, 2]}}
        back = fidelity.reassemble(fidelity.explode([element]))
        self.assertEqual(back[0]["someFieldFrom2027"], {"deep": [1, 2]})

    def test_an_element_without_an_id_does_not_gain_one(self):
        back = fidelity.reassemble(fidelity.explode([{"type": "rectangle", "x": 0}]))
        self.assertNotIn("id", back[0])

    def test_rows_may_arrive_as_plain_dicts(self):
        rows = [r.__dict__ for r in fidelity.explode(corpus.elements("freedraw"))]
        back = fidelity.reassemble(rows)
        self.assertEqual(back, corpus.elements("freedraw"))

    def test_a_corrupt_remainder_degrades_to_the_typed_columns(self):
        rows = fidelity.explode([{"id": "a", "type": "rectangle", "x": 5, "y": 6}])
        broken = dict(rows[0].__dict__, json="{not json")
        back = fidelity.reassemble([broken])
        self.assertEqual(back, [{"id": "a", "type": "rectangle", "x": 5, "y": 6}])

    def test_non_dict_entries_are_dropped_rather_than_stored(self):
        self.assertEqual(fidelity.explode(["nonsense", None, 7]), [])

    def test_columns_are_extracted_out_of_the_remainder(self):
        row = fidelity.explode([{"id": "a", "type": "rectangle", "x": 1, "seed": 9}])[0]
        rest = json.loads(row.json)
        self.assertNotIn("x", rest)
        self.assertEqual(rest["seed"], 9)


class TestAssets(unittest.TestCase):
    def test_referenced_ids_are_found(self):
        self.assertEqual(
            fidelity.file_ids(corpus.elements("image-and-files")),
            {"f-abc123", "f-orphan"},
        )

    def test_a_deleted_element_still_holds_its_file(self):
        # Excalidraw keeps isDeleted elements so undo can restore them; an undo
        # that restores an image whose file was collected restores a broken one.
        deleted = [e for e in corpus.elements("image-and-files") if e.get("isDeleted")]
        self.assertTrue(deleted)
        self.assertIn("f-orphan", fidelity.file_ids(deleted))

    def test_unreferenced_files_are_the_collectable_ones(self):
        scene = corpus.scene("image-and-files")
        self.assertEqual(
            fidelity.unreferenced_files(scene["elements"], scene["files"]),
            {"f-unreferenced"},
        )

    def test_no_elements_means_every_file_is_unreferenced(self):
        scene = corpus.scene("image-and-files")
        self.assertEqual(
            fidelity.unreferenced_files([], scene["files"]),
            set(scene["files"]),
        )


if __name__ == "__main__":
    unittest.main()
