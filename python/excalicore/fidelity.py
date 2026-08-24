"""Storing Excalidraw elements without breaking them.

An Excalidraw element carries fields no application should author and none may
discard: ``seed`` and ``versionNonce`` feed the rough-renderer and the conflict
resolver, ``version`` and ``updated`` order concurrent edits, ``index`` fixes
z-order, ``boundElements`` holds the back-references that keep labels attached
to their shapes. Normalize any of them away and the canvas does not raise — it
fails SILENTLY: a label detaches, a shape re-renders with a different hand, an
edit is quietly dropped on the next merge.

So the storage rule is: extract the few columns worth querying, and keep
EVERYTHING else verbatim. The remainder is the arbiter, because it holds
whatever the element actually said, including keys this module has never heard
of. That makes the round trip exact by construction rather than by an
ever-growing list of known fields.

These functions are pure. They return and accept plain rows; the application
owns its table, its SQL, and its transaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Fields an application must never author, normalize, or drop. Named here so a
# reader knows why the remainder is stored verbatim; nothing enforces the list
# at runtime, because the point is precisely NOT to enumerate what to keep.
BOOKKEEPING: frozenset[str] = frozenset({
    "seed", "version", "versionNonce", "index", "updated", "boundElements",
})

# The columns worth extracting: enough to query, order, and bound-box a scene
# without parsing every remainder. Deliberately excludes style — style is not
# queried, and every extracted column is a fidelity risk.
COLUMNS: tuple[str, ...] = ("id", "type", "x", "y", "width", "height", "angle")


@dataclass(frozen=True)
class ElementRow:
    """One element, ready to insert: typed columns plus the verbatim remainder.

    ``anonymous`` marks an element that arrived with no id of its own. The
    generated key keeps it addressable in storage, and :func:`reassemble` knows
    not to hand a fabricated id back to the canvas.
    """

    element_id: str
    z: int
    type: str
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    angle: float | None
    json: str
    anonymous: bool = False


def explode(elements: list[Any], *, anon_prefix: str = "anon-") -> list[ElementRow]:
    """Elements to storage rows, in array order.

    ``z`` is the array index: Excalidraw's element order IS its paint order, so
    it must be stored explicitly and read back with ORDER BY.
    """
    rows: list[ElementRow] = []
    z = 0
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        raw_id = element.get("id")
        anonymous = not (isinstance(raw_id, str) and raw_id)
        # A column carries a value only when there IS one. A key whose value is
        # None stays in the remainder, because a NULL column cannot distinguish
        # "the element said null" from "the element never said it" — and losing
        # that difference is exactly the silent damage this module exists to
        # prevent.
        rest = {
            k: v for k, v in element.items()
            if k not in COLUMNS or v is None
        }
        rows.append(ElementRow(
            element_id=f"{anon_prefix}{z}" if anonymous else str(raw_id),
            z=z,
            type=str(element.get("type") or ""),
            x=element.get("x"), y=element.get("y"),
            width=element.get("width"), height=element.get("height"),
            angle=element.get("angle"),
            json=json.dumps(rest),
            anonymous=anonymous,
        ))
        z += 1
    return rows


def reassemble(rows: Any, *, anon_prefix: str = "anon-") -> list[dict[str, Any]]:
    """Storage rows back to elements, exactly, in z order.

    Accepts anything row-like that supports ``row["column"]`` — a
    :class:`ElementRow`, a ``sqlite3.Row``, or a plain dict — so an application
    can pass its cursor straight through.

    Typed columns are re-inserted ONLY when the column holds a value. Anything
    the element said as null was left in the remainder by :func:`explode`, so
    the remainder is the arbiter: an element that never had an ``angle`` must
    not gain one on the way back, and one that said ``"angle": null`` must not
    lose it.
    """
    out: list[dict[str, Any]] = []
    for row in _ordered(rows):
        get = _getter(row)
        try:
            element = json.loads(get("json") or "{}")
        except ValueError:
            element = {}
        if not isinstance(element, dict):
            element = {}
        element_id = get("element_id")
        anonymous = _truthy(get("anonymous")) or (
            isinstance(element_id, str) and element_id.startswith(anon_prefix)
        )
        if not anonymous and element_id is not None:
            element["id"] = element_id
        if get("type"):
            element["type"] = get("type")
        for column in ("x", "y", "width", "height", "angle"):
            if get(column) is not None:
                element[column] = get(column)
        out.append(element)
    return out


def file_ids(elements: list[Any]) -> set[str]:
    """Every asset id the elements reference — the roots for asset collection.

    Deleted elements count: Excalidraw keeps ``isDeleted`` elements in the array
    so an undo can bring them back, and an undo that restores an image whose
    file was collected restores a broken image.
    """
    found: set[str] = set()
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        value = element.get("fileId")
        if value:
            found.add(str(value))
    return found


def unreferenced_files(elements: list[Any], files: Any) -> set[str]:
    """Asset ids present in ``files`` that no element references."""
    if not isinstance(files, dict):
        return set()
    return {str(k) for k in files} - file_ids(elements)


def _ordered(rows: Any) -> list[Any]:
    materialized = list(rows or [])
    return sorted(materialized, key=lambda r: _getter(r)("z") or 0)


def _getter(row: Any):
    if isinstance(row, ElementRow):
        return lambda key: getattr(row, key, None)
    if isinstance(row, dict):
        return row.get
    def _from_row(key: str) -> Any:
        try:
            return row[key]
        except (IndexError, KeyError):
            return None
    return _from_row


def _truthy(value: Any) -> bool:
    return bool(value) and value not in (0, "0", "")
