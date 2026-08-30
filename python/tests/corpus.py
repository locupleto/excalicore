"""Loading the shared golden corpus.

The corpus sits at the repository root, not under a language, because the
Python and TypeScript halves must agree about the same scenes. A fixture that
only one half can read is how the two halves drift.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2] / "corpus"
SCENES = ROOT / "scenes"
REPLIES = ROOT / "replies"
GEOMETRY = ROOT / "geometry"


def scene(name: str) -> dict[str, Any]:
    return json.loads((SCENES / f"{name}.json").read_text())


def elements(name: str) -> list[dict[str, Any]]:
    return scene(name)["elements"]


def reply(name: str) -> str:
    return (REPLIES / f"{name}.txt").read_text()


def scene_names() -> list[str]:
    return sorted(p.stem for p in SCENES.glob("*.json"))


def geometry_fixture(name: str) -> dict[str, Any]:
    """One of ``corpus/geometry/*.json`` — each a ``{doc, cases}`` object,
    ``doc`` saying what shape its cases have so a reader (or the TypeScript
    half) can understand the file without a Python test alongside it.
    Mirrors ``typescript/tests/corpus.ts``'s ``geometryFixture``."""
    return json.loads((GEOMETRY / f"{name}.json").read_text())
