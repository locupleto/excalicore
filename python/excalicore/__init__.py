"""excalicore — the parts of an Excalidraw-backed application that are the same
in every Excalidraw-backed application.

``scene``
    The bridge between a canvas and a language model: compacting a scene into a
    prompt-sized skeleton, and extracting a validated merge patch from a reply.

``fidelity``
    Storing elements without silently breaking them: exact explode/reassemble,
    and the asset references that decide what may be collected.

Both are pure — no I/O, no database, no framework, no opinion about what the
elements mean. Applications keep their own tables, prompts, and vocabulary.
"""

from __future__ import annotations

from . import fidelity, scene

__all__ = ["fidelity", "scene", "__version__"]

__version__ = "0.1.0"
