"""The vocabulary contract, against the same corpus as the TypeScript half."""

from __future__ import annotations

import json
import unittest

from excalicore import vocabulary

from . import corpus

VOCABULARIES = corpus.ROOT / "vocabularies"


def fixture(name: str) -> dict:
    return json.loads((VOCABULARIES / f"{name}.json").read_text())


def vocabulary_names() -> list[str]:
    return sorted(
        p.stem for p in VOCABULARIES.glob("*.json") if p.stem not in ("rejected", "graphs")
    )


class TestValidate(unittest.TestCase):
    def test_every_corpus_vocabulary_validates_clean(self):
        names = vocabulary_names()
        self.assertGreaterEqual(len(names), 2)
        for name in names:
            self.assertEqual(vocabulary.validate(fixture(name)), [], name)

    def test_every_rejected_vocabulary_yields_exactly_the_expected_sentences(self):
        cases = fixture("rejected")["cases"]
        self.assertGreaterEqual(len(cases), 14)
        for case in cases:
            errors = vocabulary.validate(case["vocabulary"])
            self.assertEqual(sorted(errors), sorted(case["expect"]), case["reason"])
            for e in errors:
                self.assertTrue(e.endswith("."), e)


class TestCheck(unittest.TestCase):
    def test_every_graph_case_yields_exactly_the_expected_sentences(self):
        cases = fixture("graphs")["cases"]
        self.assertGreaterEqual(len(cases), 15)
        for case in cases:
            v = fixture(case["vocabulary"])
            errors = vocabulary.check(v, case["graph"])
            self.assertEqual(sorted(errors), sorted(case["expect"]), case["name"])

    def test_check_raises_when_the_vocabulary_itself_is_not_valid(self):
        bad = {"name": "bad", "kinds": [{"name": "a"}]}
        with self.assertRaises(vocabulary.VocabularyError) as ctx:
            vocabulary.check(bad, {"subjects": [], "connections": []})
        self.assertTrue(any("needs a role" in e for e in ctx.exception.errors))


class TestLookups(unittest.TestCase):
    def test_kinds_returns_kinds_in_declared_order_filtered_by_role(self):
        bastion = fixture("bastion")
        nodes = vocabulary.kinds(bastion, "node")
        self.assertEqual([k["name"] for k in nodes], ["actor", "process", "datastore", "external_service"])
        containers = vocabulary.kinds(bastion, "container")
        self.assertEqual([k["name"] for k in containers], ["zone"])
        connectors = vocabulary.kinds(bastion, "connector")
        self.assertEqual([k["name"] for k in connectors], ["flow"])
        self.assertEqual(len(vocabulary.kinds(bastion)), 6)

    def test_kind_finds_a_kind_by_name(self):
        bastion = fixture("bastion")
        self.assertEqual(vocabulary.kind(bastion, "datastore")["name"], "datastore")
        self.assertIsNone(vocabulary.kind(bastion, "ghost"))

    def test_stencil_for_resolves_a_kind_to_its_default_stencil(self):
        bastion = fixture("bastion")
        self.assertEqual(vocabulary.stencil_for(bastion, "datastore"), "bastion-datastore")
        self.assertIsNone(vocabulary.stencil_for(bastion, "zone"))
