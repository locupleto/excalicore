"""Check this package against an existing implementation of the same code.

Anyone migrating a project onto excalicore has a working copy of these
functions already, and the only migration worth doing is one that changes no
behaviour. This test runs the whole corpus through both implementations and
asserts identical output, which turns "the switch is safe" into a measurement
rather than a hope.

Point it at your own files:

    EXCALICORE_PARITY_SOURCES=/path/to/your/scene_code.py python -m unittest ...

Several sources may be given, separated by commas. Each is expected to define
private functions named ``_compact``, ``_extract_scene``, ``_rdp``,
``_stroke_summary``, ``_sane_geometry`` and ``_valid_scene``. They are compiled
out of the file's syntax tree in isolation rather than imported, so a module
that also pulls in databases or network clients still works as a source.

The test skips when no source is configured.
"""

from __future__ import annotations

import ast
import json
import math
import os
import pathlib
import re
import unittest
from typing import Any

from excalicore import scene

from . import corpus

SOURCES_ENV = "EXCALICORE_PARITY_SOURCES"

# Module-level names the functions under test close over.
_CONSTANTS = {
    "_KEEP", "_OPAQUE_TYPES", "_MAX_STROKE_POINTS", "_MAX_COORD",
    "_LABEL_TAIL", "_FENCE_HEAD", "_decoder",
}
_FUNCTIONS = {
    "_rdp", "_stroke_summary", "_compact", "_sane_geometry",
    "_valid_scene", "_extract_scene",
}


def _load(path: pathlib.Path) -> dict[str, Any] | None:
    """The functions under test, compiled from a file without importing it."""
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


def _configured() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for raw in (os.environ.get(SOURCES_ENV) or "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        path = pathlib.Path(entry).expanduser()
        loaded = _load(path)
        if loaded:
            found[path.name] = loaded
    return found


ORIGINALS = _configured()


class TestParity(unittest.TestCase):
    def setUp(self):
        if not ORIGINALS:
            self.skipTest(f"set {SOURCES_ENV} to compare against an implementation")

    def test_compact_matches(self):
        for source, original in ORIGINALS.items():
            for name in corpus.scene_names():
                with self.subTest(source=source, scene=name):
                    elements = corpus.elements(name)
                    self.assertEqual(scene.compact(elements),
                                     original["_compact"](elements))

    def test_patch_extraction_matches(self):
        for source, original in ORIGINALS.items():
            for path in sorted(corpus.REPLIES.glob("*.txt")):
                with self.subTest(source=source, reply=path.stem):
                    message = path.read_text()
                    self.assertEqual(scene.extract_patch(message),
                                     original["_extract_scene"](message))

    def test_simplification_matches(self):
        points = corpus.elements("freedraw")[0]["points"]
        for source, original in ORIGINALS.items():
            for eps in (0.5, 1.0, 4.0, 32.0):
                with self.subTest(source=source, eps=eps):
                    self.assertEqual(scene.rdp(points, eps),
                                     original["_rdp"](points, eps))


if __name__ == "__main__":
    unittest.main()
