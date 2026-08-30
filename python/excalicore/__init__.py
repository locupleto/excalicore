"""excalicore — the parts of an Excalidraw-backed application that are the same
in every Excalidraw-backed application.

``geometry``
    The lowest module: box arithmetic, which face an arrow leaves and
    arrives on, a bent route remembered as a shape rather than a place, an
    arrow's kind read out of Excalidraw's two unrelated fields, and greedy
    word-wrap to a column budget. ``stencils`` and ``scene`` import their box
    arithmetic from here.

``scene``
    The bridge between a canvas and a language model: compacting a scene into a
    prompt-sized skeleton, and extracting a validated merge patch from a reply.

``fidelity``
    Storing elements without silently breaking them: exact explode/reassemble,
    and the asset references that decide what may be collected.

``stencils``
    The contract a vocabulary element keeps, held on the server: validating a
    stencil, choosing a body for a library item, deriving the frame and anchors.

``vocabulary``
    The form of an application's vocabulary — its kinds, containment and
    connection rules — and the checks it implies: validating the document,
    checking a graph against it, and the lookups a server's delta gate needs.

All are pure — no I/O, no database, no framework, no opinion about what the
elements mean. Applications keep their own tables, prompts, and vocabulary.
"""

from __future__ import annotations

from . import fidelity, geometry, scene, stencils, vocabulary

__all__ = ["fidelity", "geometry", "scene", "stencils", "vocabulary", "__version__"]

__version__ = "0.7.0"
