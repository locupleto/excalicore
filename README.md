# excalicore

The parts of an Excalidraw-backed application that are the same in every
Excalidraw-backed application.

Excalidraw is a canvas library. It hands you an array of elements and leaves
everything else to you — and "everything else" turns out to be the same short
list of problems each time: how to show a board to a language model without
drowning it in bookkeeping, how to accept the model's answer without letting a
garbled reply wreck the canvas, and how to store elements in a database and get
them back unbroken.

None of that is application logic, but all of it is subtle enough to get wrong
quietly. This package is that list, solved once.

## `excalicore.scene` — between a canvas and a language model

A raw Excalidraw scene is far too wide to put in a prompt, and most of its
width is bookkeeping a model must never author. `compact()` projects it onto a
prompt-sized *skeleton dialect*:

- text bound to a container folds into that container's `label`, so an echoed
  label cannot detach from its shape or duplicate;
- arrow bindings become `start`/`end` id references, and their raw points are
  dropped, because bound arrows are re-routed on conversion anyway;
- freehand strokes become a bounded, simplified polyline in absolute board
  coordinates, so a 900-point scribble costs no more than a 40-point one;
- grouped symbols appear as a single entry, addressable by the group id rather
  than as the dozen primitives they are drawn from;
- images and other content a model cannot faithfully re-emit appear as
  read-only geometry: visible and deletable, but not re-drawable.

`extract_patch()` handles the return trip. A reply is prose that may end in one
JSON object, and that object is a **merge patch** — added or changed elements
plus ids to delete — never a whole board. The inversion is the point: with a
patch, a lazy partial reply is correct behaviour and destruction requires
explicit intent, where a whole-board reply silently deletes everything the model
forgot to mention.

Validation is strict all-or-nothing. One malformed element, or a single
coordinate far enough out to be a hallucination rather than a layout, rejects
the entire patch. A half-garbled reply can never half-apply.

## `excalicore.fidelity` — storing elements without breaking them

An element carries fields no application should author and none may discard.
`seed` and `versionNonce` feed the rough-renderer and the conflict resolver,
`version` and `updated` order concurrent edits, `index` fixes z-order, and
`boundElements` holds the back-references that keep labels attached to shapes.

Normalize one away and the canvas does not raise. It fails **silently**: a
label detaches, a shape re-renders with a different hand, an edit is quietly
dropped on the next merge. The damage surfaces days later, in a board nobody
was watching.

So `explode()` extracts only the few fields worth querying — id, type, and
bounds — and keeps everything else verbatim; `reassemble()` is its exact
inverse. The verbatim remainder is the arbiter, which makes the round trip
exact by construction rather than by an ever-growing list of fields somebody
has to remember to update. A key the element never carried is not invented, a
key it set to null is not lost, and a field added by a future Excalidraw
release passes through untouched.

`file_ids()` and `unreferenced_files()` give asset collection its roots.
Deleted elements count as references: Excalidraw keeps them in the array so
undo can restore them, and an undo that restores an image whose file was
collected restores a broken image.

### `stencils` — the contract a vocabulary element keeps (both halves)

An application has a graphical vocabulary — a data store, a person, a server.
What such an element *means* belongs to the application; what it looks like
belongs to whoever drew it; what it must *provide* — one bindable body, a
frame back to the subject's box, a label slot, decorations anchored to the
body, one group, one tag namespace — is the contract in
`typescript/src/stencils.ts`. `instantiate()` places a stencil so that
`frameOf()` gives the subject's box back; `fromLibraryItem()` turns a symbol
drawn on any canvas into one; `sweep()` removes an instance whole. The Python
`excalicore.stencils` holds the same validator and the same derivations
(`validate`, `default_roles`, `from_library_item`, `subject_box`), so a server
can refuse a symbol at import time with a sentence — both halves are tested
against `corpus/stencils`. See `typescript/README.md` and `docs/design.md`.

## What is deliberately not here

No UI components, no Excalidraw wrapper, no prompt text, no HTTP layer, no
database schema, no layout engine, no palette, and no shelf of stencils —
the library defines what a stencil must provide and stores none. Both modules are pure functions — no
I/O, no framework, and no opinion about what the elements mean. Your
application keeps its own tables, prompts, and vocabulary.

## Install

```
pip install "excalicore @ git+https://github.com/locupleto/excalicore@v0.1.0#subdirectory=python"
```

Pin by tag. Canvas behaviour is the kind of thing that should only ever change
when you decide it does, never on an unrelated `git pull`.

## Use

```python
from excalicore import scene, fidelity

skeleton = scene.compact(elements)            # -> put in the prompt
prose, patch = scene.extract_patch(reply)     # -> patch is None if nothing valid

rows = fidelity.explode(elements)             # -> insert as you like
elements = fidelity.reassemble(rows)          # -> exactly what went in
```

Every tuning constant — which fields to keep, which types are read-only, the
polyline budget, the coordinate bound — is a keyword argument with a sensible
default, so a dialect can be adjusted without forking the module.

## Tests

```
cd python && python -m unittest discover -s tests -t .
```

The suite runs against a corpus of real captured scenes and real model replies
at `corpus/`, shared with the TypeScript half so both agree about the same
fixtures. See `corpus/README.md`.

`tests/test_parity.py` is a tool for anyone migrating off their own copy of
this code: point it at your existing implementation and it asserts that this
package produces identical output across the whole corpus. It skips when no
source is configured.

## Status

`0.x` — the API may still change. A module is added here when a second
independent use has proved its shape; until then it stays in the application
that needs it, because a design with one user is not yet a general one.

## Layout

```
python/       the installable Python package and its tests
typescript/   the browser half — stencils written, geometry and contrast planned; see its README
package.json  the npm package (root, so a git dependency can find it); builds typescript/dist on install
corpus/       golden scenes and model replies, shared by both halves
docs/         design rationale
```
