# Migration notes (temporary)

A working record of the one-time move from copied implementations to this
package. It is not part of the library's documentation and carries no design
rationale — delete this file once every application has adopted, and certainly
before publishing the repository.

## Where the code came from

Three applications each carried their own copy. Comparing Python function
bodies with docstrings and comments stripped, `the-armory/backend/sketch.py`
against `the-academy/backend/board.py`:

```
_compact          IDENTICAL CODE      _sane_geometry    IDENTICAL CODE
_extract_scene    IDENTICAL CODE      _stroke_summary   IDENTICAL CODE
_rdp              IDENTICAL CODE      _valid_scene      IDENTICAL CODE
```

The frontend pair `sketchGeometry.ts` and `boardGeometry.ts` are 379 lines each
and differ on four lines, all inside comments.

The one-step wipe guard exists in three schema shapes: `sketch_boards.prev_scene`
columns in the-armory, a `board_stash` table in the-academy, and a
`diagram_annotation_stash` table in the-bastion.

`fidelity` was generalized from the-bastion's `backend/reconcile.py`; the other
two applications store whole scenes as opaque blobs and are exposed to the
failure it prevents.

## Adoption order

1. **the-academy first.** It holds the copy rather than the original, so a bad
   extraction cannot reach the Control Center, and adopting in a non-origin
   application is the only real test of whether the API is generic. Success is
   `board.py` losing roughly 200 lines with its existing tests untouched and
   still passing.
2. **then the-armory**, the same deletion at higher stakes, now de-risked.
3. **then the-bastion**, for `fidelity` only at this stage.

## Running the parity check during adoption

```
EXCALICORE_PARITY_SOURCES="\
$HOME/../the-armory/backend/sketch.py,\
$HOME/../the-academy/backend/board.py" \
  python -m unittest discover -s tests -t .
```

Or, from the directory the repositories are cloned into:

```
cd excalicore/python
EXCALICORE_PARITY_SOURCES=../../the-armory/backend/sketch.py,../../the-academy/backend/board.py \
  python -m unittest tests.test_parity -v
```

Confirmed byte-identical output for `compact`, `extract_patch`, and `rdp`
against both applications on 2026-08-24, across every corpus fixture.

## Changes made to the code while lifting it

- `_valid_scene` became `valid_patch`. Both copies validated a merge patch, not
  a scene; the old name was a trap for a future reader.
- Module constants became keyword defaults.
- `compact` handles every read-only type through one branch. The originals
  special-cased `image` and let a raw element typed `stamp` fall through to the
  generic path. The corpus confirms identical output on every fixture.
- `explode` leaves a null-valued key in the verbatim remainder instead of
  extracting it to a NULL column. The-bastion's version dropped such keys on
  the way back; found by the round-trip test on its first run.

## Still to extract

The `geometry` and `contrast` modules of the TypeScript half, per
`typescript/README.md`. Their sources are
`the-armory/frontend/src/pages/{sketchGeometry,sketchColors}.ts` and
`Sketch.tsx`, against `the-academy/frontend/src/pages/{boardGeometry,chalkColors}.ts`
and `Board.tsx`.

`stencils` (2026-08-29) was not extracted from a copy; it was designed as the
contract under the Bastion's glyph code (`frontend/src/render.ts`) and the
Armory's stamp shelf (`Sketch.tsx` `expandStamp`), which each held half of
it. The applications still draw their own way; moving them onto the module is
the next step, and `stamp` / `stampGroup` are read as aliases until they do.

The view-store layer — per-diagram object rows over a generic core, with
application rules as separately droppable database constraints — lives in
the-bastion's `backend/db.py` (`_VIEW_SCHEMA` and `_VIEW_CONSTRAINTS`). It has
one consumer and stays there until a second application needs it.
