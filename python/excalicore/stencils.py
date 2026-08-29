"""The stencil contract, server side.

The TypeScript half places stencils; this half lets a server accept one.
An application that imports a symbol into its shelf — copying a library
item from another application, taking an upload — must refuse a symbol that
does not keep the contract *at load time*, with a sentence, rather than
store a thing nobody can connect to and find out at draw time. The rules are
the same six as in ``typescript/src/stencils.ts``:

1. exactly one element carries role ``body``, and it is a bindable type;
2. the body carries the ``frame`` — the subject's box relative to the body;
3. at most one element carries role ``label``, and it is a text;
4. everything else is a ``decoration`` hung on the body by an anchor;
5. all parts of an instance share one group (an instance matter — not
   checked on a definition);
6. tags live in ``customData.stencil``.

:func:`from_library_item` derives what a role map does not give — the frame
from the drawing's box, an anchor from where each part sits on the body —
exactly as the TypeScript ``fromLibraryItem`` does, so a stencil accepted here
instantiates there without surprise. Both halves are tested against
``corpus/stencils``.

Pure functions, no I/O.
"""

from __future__ import annotations

import math
from typing import Any

ROLES: frozenset[str] = frozenset({"body", "label", "decoration"})
SIZE_MODES: frozenset[str] = frozenset({"fit", "fixed"})

# Types an arrow can bind to. ``line``, ``arrow``, ``freedraw`` and ``text``
# are not among them: Excalidraw's converter throws on a binding to those.
BINDABLE_TYPES: frozenset[str] = frozenset({"rectangle", "ellipse", "diamond", "image"})


class StencilError(ValueError):
    """A stencil that does not keep the contract; ``errors`` are sentences."""

    def __init__(self, name: str, errors: list[str]) -> None:
        super().__init__(f'Stencil "{name}" is not valid: {" ".join(errors)}')
        self.name = name
        self.errors = errors


def tag_of(element: Any) -> dict[str, Any] | None:
    """The stencil tag on an element, or None."""
    if not isinstance(element, dict):
        return None
    cd = element.get("customData")
    if not isinstance(cd, dict):
        return None
    tag = cd.get("stencil")
    if not isinstance(tag, dict) or not isinstance(tag.get("role"), str):
        return None
    return tag


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else 0.0


def _finite(*values: Any) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _box(el: dict[str, Any]) -> tuple[float, float, float, float]:
    return _num(el.get("x")), _num(el.get("y")), _num(el.get("width")), _num(el.get("height"))


def _bbox(els: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    if not els:
        return None
    boxes = [_box(e) for e in els]
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return x1, y1, x2 - x1, y2 - y1


def _id(el: dict[str, Any]) -> str:
    return el["id"] if isinstance(el.get("id"), str) else "(no id)"


def validate(elements: list[Any]) -> list[str]:
    """The contract, checked. Empty list means valid; otherwise sentences."""
    errors: list[str] = []
    live = [e for e in elements or [] if isinstance(e, dict) and not e.get("isDeleted")]
    if not live:
        return ["A stencil needs at least one element."]

    bodies: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for el in live:
        tag = tag_of(el)
        if tag is None:
            errors.append(f'Element "{_id(el)}" has no role; every part is a body, a label or a decoration.')
            continue
        role = tag["role"]
        if role == "body":
            bodies.append(el)
        elif role == "label":
            labels.append(el)
        elif role != "decoration":
            errors.append(f'Element "{_id(el)}" has an unknown role "{role}".')

    if len(bodies) != 1:
        which = f" ({', '.join(_id(b) for b in bodies)})" if bodies else ""
        errors.append(
            f'A stencil needs exactly one element with role "body"; this one has {len(bodies)}{which}.'
        )
    body = bodies[0] if len(bodies) == 1 else None
    if body is not None:
        if str(body.get("type")) not in BINDABLE_TYPES:
            errors.append(
                "The body must be a rectangle, ellipse, diamond or image so arrows can bind to it; "
                f'"{body.get("type")}" cannot be bound to.'
            )
        frame = (tag_of(body) or {}).get("frame")
        if not isinstance(frame, dict):
            errors.append("The body must carry a frame {dx, dy, sw, sh}: the subject's box relative to the body.")
        elif (not _finite(frame.get("dx"), frame.get("dy"), frame.get("sw"), frame.get("sh"))
              or frame["sw"] <= 0 or frame["sh"] <= 0):
            errors.append("The body's frame needs finite dx and dy and positive sw and sh.")

    if len(labels) > 1:
        errors.append(
            f'At most one element may carry role "label"; found {len(labels)} '
            f"({', '.join(_id(l) for l in labels)})."
        )
    if labels and body is not None and isinstance(body.get("label"), dict):
        errors.append(
            f'The body "{_id(body)}" already carries a label property; a label element on top of it is one label too many.'
        )
    for label in labels:
        if label.get("type") != "text":
            errors.append(f'The label must be a text element; "{_id(label)}" is a {label.get("type")}.')
        container = label.get("containerId")
        if container is not None and body is not None and container != body.get("id"):
            errors.append(
                f'A bound label\'s containerId must be the body "{_id(body)}"; "{_id(label)}" is bound to "{container}".'
            )

    for el in live:
        tag = tag_of(el)
        if tag is None or tag["role"] == "body":
            continue
        anchor = tag.get("anchor")
        if anchor is not None and not (isinstance(anchor, dict) and _finite(anchor.get("u"), anchor.get("v"))):
            errors.append(f'Part "{_id(el)}": anchor needs finite u and v.')
        offset = tag.get("offset")
        if offset is not None and not (isinstance(offset, dict) and _finite(offset.get("dx"), offset.get("dy"))):
            errors.append(f'Part "{_id(el)}": offset needs finite dx and dy.')
        size = tag.get("size")
        if size is not None and size not in SIZE_MODES:
            errors.append(f'Part "{_id(el)}": size must be "fit" or "fixed", not "{size}".')
        variant = tag.get("variant")
        if variant is not None and (not isinstance(variant, str) or not variant):
            errors.append(f'Part "{_id(el)}": variant must be a non-empty string.')
        if variant is not None and tag["role"] == "label":
            errors.append(f'Part "{_id(el)}": a label cannot be a variant; only decorations are optional.')
    return errors


def default_roles(item: dict[str, Any]) -> dict[str, Any]:
    """The role map a library item implies on its own.

    Roles its elements already carry in ``customData.stencil`` win; when none
    of them is a body, the largest element of a bindable type is the body —
    the head of a figure, the chassis of a machine. An item with nothing
    bindable gets an empty map, which :func:`from_library_item` then refuses.
    """
    roles: dict[str, Any] = {}
    live = [e for e in item.get("elements") or [] if isinstance(e, dict) and not e.get("isDeleted")]
    has_body = False
    for el in live:
        tag = tag_of(el)
        if tag is not None and isinstance(el.get("id"), str):
            roles[el["id"]] = dict(tag)
            if tag["role"] == "body":
                has_body = True
    if not has_body:
        best: dict[str, Any] | None = None
        best_area = -1.0
        for el in live:
            if str(el.get("type")) not in BINDABLE_TYPES or not isinstance(el.get("id"), str):
                continue
            _, _, w, h = _box(el)
            area = abs(w) * abs(h)
            if best is None or area > best_area:
                best, best_area = el, area
        if best is not None:
            roles[best["id"]] = "body"
    return roles


def from_library_item(item: dict[str, Any], roles: dict[str, Any]) -> dict[str, Any]:
    """A stencil ``{"name", "elements"}`` from a library item and a role map.

    Elements not named in the map are decorations. A missing frame is the
    box of everything but the label, relative to the body; a missing anchor
    is where the part's origin sits on the body's box; size defaults to
    ``fit`` for shapes and ``fixed`` for text. Raises :class:`StencilError`
    when the result does not keep the contract.
    """
    name = str(item.get("name") or "").strip()
    if not name:
        raise StencilError("(unnamed)", ["A stencil needs a name."])
    source = [e for e in item.get("elements") or [] if isinstance(e, dict) and not e.get("isDeleted")]

    def spec_of(el: dict[str, Any]) -> dict[str, Any]:
        spec = roles.get(el["id"]) if isinstance(el.get("id"), str) else None
        if spec is None:
            return {"role": "decoration"}
        return {"role": spec} if isinstance(spec, str) else dict(spec)

    tagged = [(el, spec_of(el)) for el in source]
    bodies = [el for el, spec in tagged if spec.get("role") == "body"]
    body = bodies[0] if len(bodies) == 1 else None
    body_box = _box(body) if body is not None else None
    subject = _bbox([el for el, spec in tagged if spec.get("role") != "label"])

    elements: list[dict[str, Any]] = []
    for el, spec in tagged:
        tag = dict(spec)
        if spec.get("role") == "body":
            if "frame" not in tag and body_box is not None and subject is not None:
                bx, by, bw, bh = body_box
                sx, sy, sw, sh = subject
                tag["frame"] = {
                    "dx": sx - bx, "dy": sy - by,
                    "sw": sw / bw if bw else 1, "sh": sh / bh if bh else 1,
                }
        else:
            bound = spec.get("role") == "label" and isinstance(el.get("containerId"), str)
            if not bound and "anchor" not in tag and body_box is not None:
                bx, by, bw, bh = body_box
                x, y, _, _ = _box(el)
                tag["anchor"] = {"u": (x - bx) / bw if bw else 0, "v": (y - by) / bh if bh else 0}
            if not bound and "offset" not in tag:
                tag["offset"] = {"dx": 0, "dy": 0}
            if "size" not in tag:
                tag["size"] = "fixed" if el.get("type") == "text" else "fit"
        cd = el.get("customData") if isinstance(el.get("customData"), dict) else {}
        elements.append({**el, "customData": {**cd, "stencil": tag}})

    errors = validate(elements)
    if errors:
        raise StencilError(name, errors)
    return {"name": name, "elements": elements}


def subject_box(elements: list[Any]) -> tuple[float, float, float, float] | None:
    """The subject's box (x, y, width, height) read off the body and its
    frame, or None. The only way back from a stencil or an instance."""
    for el in elements or []:
        tag = tag_of(el)
        if tag is not None and tag["role"] == "body" and isinstance(tag.get("frame"), dict):
            f = tag["frame"]
            if not _finite(f.get("dx"), f.get("dy"), f.get("sw"), f.get("sh")):
                return None
            x, y, w, h = _box(el)
            return x + f["dx"], y + f["dy"], w * f["sw"], h * f["sh"]
    return None
