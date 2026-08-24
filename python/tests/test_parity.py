"""Differential test against the implementations this package was lifted from.

Extraction is only safe if the extracted code behaves EXACTLY like the copies
still running in the applications. This test loads the original private
functions straight out of the sibling repositories and runs the whole corpus
through both, so "adoption is a pure deletion" is a measured claim rather than
an intention.

It skips when the sibling repositories are not checked out beside this one, so
the suite stays green on a machine that only has excalicore. Once every
application has adopted the package, this test has done its job and can go.
"""

from __future__ import annotations

import ast
import json
import math
import pathlib
import re
import unittest
from typing import Any

from excalicore import scene

from . import corpus

SIBLINGS = {
    "armory": pathlib.Path("the-armory/backend/sketch.py"),
    "academy": pathlib.Path("the-academy/backend/board.py"),
}
GIT_ROOT = corpus.ROOT.parent.parent  # the directory the repositories are cloned into

# Module-level names the lifted functions close over.
_CONSTANTS = {
    "_KEEP", "_OPAQUE_TYPES", "_MAX_STROKE_POINTS", "_MAX_COORD",
    "_LABEL_TAIL", "_FENCE_HEAD", "_decoder",
}
_FUNCTIONS = {
    "_rdp", "_stroke_summary", "_compact", "_sane_geometry",
    "_valid_scene", "_extract_scene",
}


def _load(path: pathlib.Path) -> dict[str, Any] | None:
    """The pure functions from an application module, without importing it.

    The real modules pull in databases, SSH, and HTTP clients; only these few
    functions are wanted, so they are compiled out of the AST in isolation.
    """
    if not path.exists():
        return None
    tree = ast.parse(path.read_text())
    keep = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in _FUNCTIONS)
        or (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in _CONSTANTS for t in node.targets))
    ]
    namespace: dict[str, Any] = {"json": json, "math": math, "re": re, "Any": object}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), "exec"), namespace)
    return namespace if _FUNCTIONS <= set(namespace) else None


ORIGINALS = {name: _load(GIT_ROOT / path) for name, path in SIBLINGS.items()}


class TestParity(unittest.TestCase):
    def _originals(self):
        found = {k: v for k, v in ORIGINALS.items() if v}
        if not found:
            self.skipTest("no sibling application checked out beside excalicore")
        return found

    def test_compact_matches_every_original(self):
        for app, original in self._originals().items():
            for name in corpus.scene_names():
                with self.subTest(app=app, scene=name):
                    elements = corpus.elements(name)
                    self.assertEqual(scene.compact(elements),
                                     original["_compact"](elements))

    def test_patch_extraction_matches_every_original(self):
        for app, original in self._originals().items():
            for path in sorted(corpus.REPLIES.glob("*.txt")):
                with self.subTest(app=app, reply=path.stem):
                    message = path.read_text()
                    self.assertEqual(scene.extract_patch(message),
                                     original["_extract_scene"](message))

    def test_simplification_matches_every_original(self):
        points = corpus.elements("freedraw")[0]["points"]
        for app, original in self._originals().items():
            for eps in (0.5, 1.0, 4.0, 32.0):
                with self.subTest(app=app, eps=eps):
                    self.assertEqual(scene.rdp(points, eps), original["_rdp"](points, eps))


if __name__ == "__main__":
    unittest.main()
