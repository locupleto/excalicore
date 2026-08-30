"""The vocabulary contract, server side.

An application built on excalicore has a vocabulary: its kinds, which of
them are containers, which are connectors, what may sit inside what and what
may join what. This module holds the FORM of a vocabulary and the checks a
declared one implies; it never holds a particular vocabulary — what a data
store means, and that it is a node that sits in a zone, stays with the
application.

Words: a VOCABULARY is one document per application, a name and its kinds.
A KIND has a ROLE — ``node`` (placed and may be joined), ``container``
(holds nodes and other containers) or ``connector`` (joins two subjects). A
SUBJECT is a placed thing on the board, in the application's terms; a
CONNECTION is a connector between two subjects. A GRAPH is the subjects and
connections of one model, in the neutral shape the checker reads.

:func:`validate` checks a vocabulary document itself: every kind has a name
and a role, ``within`` and ``ends`` name real kinds of the right role,
``placed``, ``directed``, ``loops`` and ``parallel`` hold their allowed
values. :func:`check` checks a graph against an already-valid vocabulary:
subjects and connections are declared once, of a known kind and the right
role, containment is honoured and free of cycles, and every connection's
ends are on the board, of an allowed pair of kinds, and — when the kind
forbids it — not a loop or a parallel of another.

Both return sentences; an empty list means valid. Identifiers are quoted,
lists of identifiers sorted. Both halves are tested against
``corpus/vocabularies/``.

Pure functions, no I/O, and this module never reads an application's tables
or tags — the graph is built and handed in.
"""

from __future__ import annotations

from typing import Any


class VocabularyError(ValueError):
    """A vocabulary that is not valid; ``errors`` are sentences."""

    def __init__(self, name: str, errors: list[str]) -> None:
        super().__init__(f'Vocabulary "{name}" is not valid: {" ".join(errors)}')
        self.name = name
        self.errors = errors


# --- small defensive readers -------------------------------------------------

def _as_object(v: Any) -> dict[str, Any] | None:
    return v if isinstance(v, dict) else None


def _as_array(v: Any) -> list[Any] | None:
    return v if isinstance(v, list) else None


def _as_string(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def _non_empty_string(v: Any) -> str | None:
    s = _as_string(v)
    return s if s else None


def _name_of(vocabulary: Any) -> str:
    obj = _as_object(vocabulary)
    return _non_empty_string(obj.get("name") if obj else None) or "(unnamed)"


def _quote_list(ids: list[str]) -> str:
    """Sorted, quoted, joined with "and": ``"a" and "b"``, ``"a", "b" and "c"``."""
    sorted_ids = sorted(ids)
    if len(sorted_ids) == 1:
        return f'"{sorted_ids[0]}"'
    head = [f'"{i}"' for i in sorted_ids[:-1]]
    return f'{", ".join(head)} and "{sorted_ids[-1]}"'


# --- validating a vocabulary --------------------------------------------------

def validate(vocabulary: Any) -> list[str]:
    """The vocabulary document, checked. Empty list means valid; otherwise
    sentences. Never raises on malformed input — a vocabulary with no name
    or no kinds is an error with a sentence, not a crash."""
    errors: list[str] = []
    v = _as_object(vocabulary)

    if not _non_empty_string(v.get("name") if v else None):
        errors.append("A vocabulary needs a name.")

    raw_kinds = _as_array(v.get("kinds")) if v else None
    if not raw_kinds:
        errors.append("A vocabulary needs at least one kind.")
    entries = raw_kinds or []

    kind_objects: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        obj = _as_object(entry)
        if obj is None:
            errors.append(f"Kind {i + 1} is not an object.")
            continue
        kind_objects.append(obj)

    known: dict[str, dict[str, Any]] = {}
    for kind in kind_objects:
        kn = _non_empty_string(kind.get("name"))
        if kn:
            known[kn] = kind

    def role_of(kn: str) -> Any:
        k = known.get(kn)
        return k.get("role") if k else None

    counts: dict[str, int] = {}
    for kind in kind_objects:
        kn = _non_empty_string(kind.get("name"))
        if kn:
            counts[kn] = counts.get(kn, 0) + 1
    for kn, count in counts.items():
        if count > 1:
            errors.append(f'Kind "{kn}" is declared twice.')

    for kind in kind_objects:
        kn = _non_empty_string(kind.get("name")) or "(unnamed)"
        role_raw = kind.get("role")
        role: str | None = None
        if "role" not in kind:
            errors.append(f'Kind "{kn}" needs a role: node, container or connector.')
        elif role_raw not in ("node", "container", "connector"):
            errors.append(
                f'Kind "{kn}" has an unknown role "{role_raw}"; a kind is a node, a container or a connector.'
            )
        else:
            role = role_raw

        # within
        has_within = "within" in kind
        if role == "connector":
            if has_within:
                errors.append(f'Kind "{kn}" is a connector and cannot sit within anything.')
        elif has_within:
            for w in _as_array(kind.get("within")) or []:
                wn = _as_string(w)
                if wn is None:
                    continue
                if wn not in known:
                    errors.append(f'Kind "{kn}" may sit within "{wn}", which is not a kind of this vocabulary.')
                elif role_of(wn) != "container":
                    errors.append(f'Kind "{kn}" may sit within "{wn}", which is not a container.')

        # placed
        placed = "sometimes"
        if "placed" in kind:
            if kind["placed"] not in ("always", "sometimes"):
                errors.append(f'Kind "{kn}" is placed "{kind["placed"]}"; a kind is placed always or sometimes.')
            else:
                placed = kind["placed"]
        if placed == "always" and not (_as_array(kind.get("within")) or []):
            errors.append(f'Kind "{kn}" is always placed but names nothing it may sit within.')

        # ends
        has_ends = "ends" in kind
        if role == "connector":
            end_list = _as_array(kind.get("ends"))
            if not end_list:
                errors.append(f'Kind "{kn}" is a connector and needs ends.')
            else:
                for entry in end_list:
                    pair = _as_array(entry)
                    if (
                        pair is None
                        or len(pair) != 2
                        or not isinstance(pair[0], str)
                        or not isinstance(pair[1], str)
                    ):
                        errors.append(f'Kind "{kn}" has an end that is not a pair of kinds.')
                        continue
                    frm, to = pair
                    if frm != "*" and frm not in known:
                        errors.append(f'Kind "{kn}" may run from "{frm}", which is not a kind of this vocabulary.')
                    if to != "*" and to not in known:
                        errors.append(f'Kind "{kn}" may run to "{to}", which is not a kind of this vocabulary.')
        elif has_ends:
            errors.append(f'Kind "{kn}" is not a connector and cannot have ends.')

        # directed, loops, parallel
        for field in ("directed", "loops", "parallel"):
            if field in kind and not isinstance(kind[field], bool):
                errors.append(f'Kind "{kn}": {field} must be true or false.')

        # stencil, label
        if "stencil" in kind and (not isinstance(kind["stencil"], str) or kind["stencil"] == ""):
            errors.append(f'Kind "{kn}" names an empty stencil.')
        if "label" in kind and (not isinstance(kind["label"], str) or kind["label"] == ""):
            errors.append(f'Kind "{kn}" has an empty label.')

    return errors


# --- containment cycles -------------------------------------------------------

def _find_cycles(edges: dict[str, str]) -> list[list[str]]:
    """Cycles in a functional graph (out-degree at most one per node): follow
    each chain, and when it revisits a node already on its own path, the tail
    from that node back to itself is a cycle. Every node is finalized once,
    so a chain that merges into an already-resolved tail or an
    already-reported cycle is not reported again."""
    cycles: list[list[str]] = []
    done: set[str] = set()
    for start in edges:
        if start in done:
            continue
        path: list[str] = []
        index_in_path: dict[str, int] = {}
        cur: str | None = start
        while cur is not None and cur not in done:
            if cur in index_in_path:
                cycles.append(path[index_in_path[cur]:])
                break
            index_in_path[cur] = len(path)
            path.append(cur)
            cur = edges.get(cur)
        done.update(path)
    return cycles


# --- checking a connector's ends ----------------------------------------------

def _ends_allow(kind: dict[str, Any], from_kind: str, to_kind: str) -> bool:
    ends = _as_array(kind.get("ends")) or []

    def matches(pattern: Any, actual: str) -> bool:
        return pattern == "*" or pattern == actual

    pairs = [p for p in (_as_array(e) for e in ends) if p is not None and len(p) == 2]
    if any(matches(p[0], from_kind) and matches(p[1], to_kind) for p in pairs):
        return True
    if kind.get("directed") is False:
        return any(matches(p[0], to_kind) and matches(p[1], from_kind) for p in pairs)
    return False


# --- checking a graph ----------------------------------------------------------

def check(vocabulary: Any, graph: Any) -> list[str]:
    """A graph against a vocabulary. Raises :class:`VocabularyError` when the
    vocabulary itself is not valid; otherwise returns violations of the
    graph as sentences, empty meaning the graph keeps the vocabulary."""
    vocab_errors = validate(vocabulary)
    if vocab_errors:
        raise VocabularyError(_name_of(vocabulary), vocab_errors)

    errors: list[str] = []
    v = _as_object(vocabulary) or {}
    kinds: dict[str, dict[str, Any]] = {}
    for entry in _as_array(v.get("kinds")) or []:
        obj = _as_object(entry)
        kn = _non_empty_string(obj.get("name")) if obj else None
        if kn and obj is not None:
            kinds[kn] = obj

    g = _as_object(graph)
    raw_subjects = (_as_array(g.get("subjects")) if g else None) or []
    subjects = [obj for s in raw_subjects if (obj := _as_object(s)) is not None]
    raw_connections = (_as_array(g.get("connections")) if g else None) or []
    connections = [obj for c in raw_connections if (obj := _as_object(c)) is not None]

    # Rule 9: declared once.
    subject_counts: dict[str, int] = {}
    for s in subjects:
        sid = _as_string(s.get("id"))
        if sid is not None:
            subject_counts[sid] = subject_counts.get(sid, 0) + 1
    for sid, count in subject_counts.items():
        if count > 1:
            errors.append(f'Subject "{sid}" is declared twice.')

    connection_counts: dict[str, int] = {}
    for c in connections:
        cid = _as_string(c.get("id"))
        if cid is not None:
            connection_counts[cid] = connection_counts.get(cid, 0) + 1
    for cid, count in connection_counts.items():
        if count > 1:
            errors.append(f'Connection "{cid}" is declared twice.')

    subject_by_id: dict[str, dict[str, Any]] = {}
    for s in subjects:
        sid = _as_string(s.get("id"))
        if sid is not None:
            subject_by_id[sid] = s

    # Rules 10 + 11: subject kind/role, then containment.
    contains_edge: dict[str, str] = {}
    for s in subjects:
        sid = _as_string(s.get("id")) or "(no id)"
        kind_name = _as_string(s.get("kind"))
        if kind_name is None or kind_name not in kinds:
            errors.append(f'Subject "{sid}" has an unknown kind "{s.get("kind")}".')
            continue
        kind = kinds[kind_name]
        if kind.get("role") == "connector":
            errors.append(
                f'Subject "{sid}" is of kind "{kind_name}", which is a connector; a subject is a node or a container.'
            )
            continue

        if "within" in s:
            target = _as_string(s.get("within"))
            if target is not None and target == sid:
                errors.append(f'Subject "{sid}" sits within itself.')
            elif target is not None:
                target_subject = subject_by_id.get(target)
                if target_subject is None:
                    errors.append(f'Subject "{sid}" sits within "{target}", which is not on the board.')
                else:
                    target_kind_name = _as_string(target_subject.get("kind"))
                    target_kind = kinds.get(target_kind_name) if target_kind_name else None
                    if target_kind is None or target_kind.get("role") != "container":
                        errors.append(f'Subject "{sid}" sits within "{target}", which is not a container.')
                    elif target_kind_name not in (_as_array(kind.get("within")) or []):
                        errors.append(
                            f'Subject "{sid}" is a "{kind_name}" and cannot sit within a "{target_kind_name}".'
                        )
                    else:
                        contains_edge[sid] = target
        elif kind.get("placed") == "always":
            errors.append(f'Subject "{sid}" is a "{kind_name}", which must sit within a container.')

    # Rule 12: containment cycles, only among edges rule 11 accepted.
    for cycle in _find_cycles(contains_edge):
        errors.append(f"Subjects {_quote_list(cycle)} contain one another.")

    # Rules 10 + 13 + 14: connections.
    parallel_groups: dict[str, list[dict[str, str]]] = {}
    for c in connections:
        cid = _as_string(c.get("id")) or "(no id)"
        kind_name = _as_string(c.get("kind"))
        if kind_name is None or kind_name not in kinds:
            errors.append(f'Connection "{cid}" has an unknown kind "{c.get("kind")}".')
            continue
        kind = kinds[kind_name]
        if kind.get("role") != "connector":
            errors.append(f'Connection "{cid}" is of kind "{kind_name}", which is not a connector.')
            continue

        frm = _as_string(c.get("from"))
        to = _as_string(c.get("to"))
        missing = False
        if frm is None or frm not in subject_by_id:
            errors.append(f'Connection "{cid}" runs from "{c.get("from")}", which is not on the board.')
            missing = True
        if to is None or to not in subject_by_id:
            errors.append(f'Connection "{cid}" runs to "{c.get("to")}", which is not on the board.')
            missing = True
        if missing:
            continue

        from_subject = subject_by_id[frm]
        to_subject = subject_by_id[to]
        from_kind = _as_string(from_subject.get("kind")) or ""
        to_kind = _as_string(to_subject.get("kind")) or ""

        if not _ends_allow(kind, from_kind, to_kind):
            errors.append(f'Connection "{cid}" is a "{kind_name}" and cannot run from a "{from_kind}" to a "{to_kind}".')

        if frm == to and kind.get("loops") is not True:
            errors.append(f'Connection "{cid}" loops "{frm}" onto itself.')

        if kind.get("parallel") is False:
            directed = kind.get("directed") is not False
            pair_key = f"{frm} {to}" if directed else " ".join(sorted([frm, to]))
            key = f"{kind_name} {pair_key}"
            parallel_groups.setdefault(key, []).append({"id": cid, "from": frm, "to": to, "kindName": kind_name})

    for group in parallel_groups.values():
        if len(group) < 2:
            continue
        first = group[0]
        for other in group[1:]:
            errors.append(
                f'Connections {_quote_list([first["id"], other["id"]])} both run between '
                f'"{first["from"]}" and "{first["to"]}"; a "{first["kindName"]}" allows one.'
            )

    return errors


# --- lookups -------------------------------------------------------------------

def kinds(vocabulary: Any, role: str | None = None) -> list[dict[str, Any]]:
    """Every kind of the vocabulary, in declared order; filtered to one role
    when given. Assumes a valid vocabulary — validate it first."""
    v = _as_object(vocabulary)
    out: list[dict[str, Any]] = []
    for entry in (_as_array(v.get("kinds")) if v else None) or []:
        obj = _as_object(entry)
        if obj is None:
            continue
        if role is not None and obj.get("role") != role:
            continue
        out.append(obj)
    return out


def kind(vocabulary: Any, name: str) -> dict[str, Any] | None:
    """The named kind, or None."""
    for k in kinds(vocabulary):
        if k.get("name") == name:
            return k
    return None


def stencil_for(vocabulary: Any, name: str) -> str | None:
    """The kind's default stencil name, or None — the application resolves
    it against its own shelf; this module never does."""
    k = kind(vocabulary, name)
    stencil = k.get("stencil") if k else None
    return stencil if isinstance(stencil, str) else None
