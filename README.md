# excalicore

The parts of an Excalidraw-backed application that are the same in every
Excalidraw-backed application — written once, tested once, and depended on by
name instead of copied.

## Why it exists

Three applications in this estate put Excalidraw in front of a model or a
database. Before this package, they shared their canvas handling by copying it.
Comparing function bodies with comments and docstrings stripped:

```
_compact          IDENTICAL CODE      _sane_geometry    IDENTICAL CODE
_extract_scene    IDENTICAL CODE      _stroke_summary   IDENTICAL CODE
_rdp              IDENTICAL CODE      _valid_scene      IDENTICAL CODE
```

Two copies of one idea, plus a 379-line frontend module duplicated with four
differing comment lines. Nothing had diverged yet — but a fix applied to one
copy would never have reached the other, and neither copy carried the element
fidelity rules the third application learned the hard way.

## What is in it

### `excalicore.scene` — the canvas/model bridge

`compact()` projects a raw scene onto a prompt-sized skeleton: the binding
graph folded into skeleton form, bound labels folded into their containers,
stamp groups shown as one symbol, strokes simplified to a bounded polyline.

`extract_patch()` takes a model's reply and returns `(prose, patch)`. The patch
is a MERGE PATCH — added or changed elements plus ids to delete — never a whole
board. That inversion matters: a lazy partial reply is then correct behaviour,
and destruction requires explicit intent. Validation is strict all-or-nothing,
so a half-garbled reply can never half-apply.

### `excalicore.fidelity` — storing elements without breaking them

An element carries fields no application should author and none may discard:
`seed`, `versionNonce`, `version`, `updated`, `index`, `boundElements`.
Normalize one away and the canvas does not raise — it fails silently.

So `explode()` extracts the few columns worth querying and keeps everything
else verbatim; `reassemble()` is its exact inverse. The remainder is the
arbiter, which makes the round trip exact by construction rather than by an
ever-growing list of known fields. `file_ids()` and `unreferenced_files()`
give asset collection its roots.

Both modules are pure: no I/O, no database, no framework, and no opinion about
what the elements mean. Applications keep their own tables, prompts, and
vocabulary.

## What is deliberately not in it

React components, an Excalidraw wrapper, prompt text or personas, an HTTP
layer, and any layout engine. The moment the core knows what a "zone" or a
"beat" is, it has stopped being a core.

## Verification

```
cd python && python -m unittest discover -s tests -t .
```

Beyond the unit tests, `tests/test_parity.py` runs the whole corpus through the
original private functions still living in the sibling applications and asserts
identical output — so "adopting this package is a pure deletion" is measured,
not hoped for. It skips when those repositories are not checked out alongside.

## Using it

Pin it by tag, per application, so adopting a new version is always a
deliberate act and never a surprise on a `git pull`:

```
excalicore @ git+https://github.com/locupleto/excalicore@v0.1.0#subdirectory=python
```

## Status

`0.x`. The two modules here have two or more consumers each and are stable in
shape. The view-store layer described in `docs/` — per-diagram object rows over
a generic core, with application rules as separate droppable constraints — has
one consumer so far and is not in this release; it should not set the API
tone for code that is already shared.

## Layout

```
python/       the installable package and its tests
typescript/   the browser half — measured, not yet extracted
corpus/       golden scenes and model replies, shared by both halves
```
