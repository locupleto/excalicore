# Design and adoption plan

## Evidence this package is built on

Measured 2026-08-24 across the three applications.

Python, comparing function bodies with docstrings and comments stripped
(`the-armory/backend/sketch.py` vs `the-academy/backend/board.py`):

```
_compact          IDENTICAL CODE      _sane_geometry    IDENTICAL CODE
_extract_scene    IDENTICAL CODE      _stroke_summary   IDENTICAL CODE
_rdp              IDENTICAL CODE      _valid_scene      IDENTICAL CODE
```

TypeScript: `sketchGeometry.ts` and `boardGeometry.ts` are 379 lines each and
differ on four lines, all of them inside comments.

Schema: one mechanism — the one-step wipe guard — exists in three shapes.
`sketch_boards.prev_scene` columns in the Armory, a `board_stash` table in the
Academy, a `diagram_annotation_stash` table in the Bastion.

The applications had not diverged in behaviour. They had diverged in prose, and
they were one bug fix away from diverging in behaviour.

## Module plan

Shipped in 0.1.0:

- `excalicore.scene` — canvas to model and back. Two consumers today.
- `excalicore.fidelity` — exact element storage and asset roots. One consumer
  today, but the other two are exposed to the failure it prevents.

Planned, in order of evidence:

- `excalicore.store` — scene persistence and the wipe guard, over a
  caller-supplied connection and a small table descriptor. Not a mini-ORM: the
  applications keep their tables and their migrations, and the package owns
  only the rule (stash one step deep, only on a wipe, swap self-inversely).
  Three consumers, three current shapes.
- `excalicore.stencils` — symbol-library footprints, menu rendering, and
  placement expansion. Expansion currently exists only in the two frontends;
  having it server-side lets a headless test verify a placement.
- TypeScript `geometry`, `contrast`, `stamps` — see `typescript/README.md`.
- `excalicore.viewstore` — `diagrams` / `diagram_objects` /
  `annotation_elements` / `diagram_files` plus a `Profile` object that declares
  an application's subject kinds and the fields each may carry, rendered into
  database triggers so the constraints are enforced below the language. One
  consumer. Held back deliberately: a single-consumer design must not set the
  API tone for code that is already shared.

## Adoption order

1. **The Academy first.** It holds the copy, not the original, so a bad
   extraction cannot reach the Control Center, and adopting in a non-origin
   application is the only real test of whether the API is generic. Success is
   `board.py` losing roughly 200 lines with its existing tests untouched and
   still passing.
2. **Then the Armory**, the same deletion with higher stakes, now de-risked.
3. **Then the Bastion**, for `fidelity` only in this release.

`tests/test_parity.py` is the safety net for steps 1 and 2: it runs the corpus
through the original private functions and asserts identical output. It has
already confirmed byte-identical behaviour for `compact`, `extract_patch`, and
`rdp` against both applications. Once every application has adopted, that test
has done its job and can go.

## Distribution

Pinned by tag per application, so adopting a new version is a deliberate act:

```
excalicore @ git+https://github.com/locupleto/excalicore@v0.1.0#subdirectory=python
```

No submodules. The applications already clone over HTTPS on the host, so this
adds no deploy machinery.

## Deviations from the code as lifted

Recorded so a reviewer comparing against the originals is not surprised.

- `_valid_scene` is now `valid_patch`. Both copies validate a merge patch, not
  a scene; the old name was a bug waiting for a reader to believe it.
- Module constants (`KEEP`, `OPAQUE_TYPES`, `MAX_STROKE_POINTS`, `MAX_COORD`)
  became keyword defaults, so an application tunes the dialect instead of
  forking the module.
- `compact` handles every opaque type through one branch. The originals
  special-cased `image` and let a raw element typed `stamp` fall through to the
  generic path. Unified; the corpus confirms identical output on every fixture.
- `fidelity.explode` leaves a key whose value is `None` in the verbatim
  remainder rather than extracting it to a NULL column. A NULL column cannot
  distinguish "the element said null" from "the element never said it", and the
  Bastion's version silently dropped such keys on the way back. Found by the
  round-trip test on the first run.
