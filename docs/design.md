# Design notes

Why the two modules are shaped the way they are. These are the decisions that
took a while to arrive at and would otherwise be re-litigated by every reader
who finds them surprising.

## A merge patch, not a scene

A model asked to modify a board can reply in two ways: with the whole board, or
with only what changes. Whole-board replies fail badly. The model summarizes,
drops what it considers unimportant, and every omission is a deletion — so a
lazy reply silently destroys work, and the failure is invisible until someone
looks for a shape that is no longer there.

A merge patch inverts the failure mode. Unmentioned elements stay. A lazy reply
is then *correct behaviour*, and destruction requires an explicit `delete` list.
The worst case becomes "nothing happened" rather than "the board is gone".

## All-or-nothing validation

A patch is accepted whole or rejected whole. The alternative — applying the
elements that parse and skipping the rest — produces a board that is neither
what the model meant nor what the user had, and it does so without any signal
that something went wrong. Partial application is how a canvas ends up in a
state no one designed.

Coordinate bounds are part of this. A model that emits `x: 4000000` has not
made a layout decision; it has hallucinated. Such a value is rejected rather
than clamped, because clamping produces a plausible-looking board built on a
number nobody chose.

## Read-only element types

Some elements cannot survive an echo through a language model:

- **Freehand strokes** are point clouds of hundreds of coordinates. A model
  cannot reproduce one, and asking it to try wastes an enormous number of
  tokens to get back a caricature of the user's own ink.
- **Images** carry a `fileId` pointing into a separate asset store. An echoed
  image loses that reference and becomes a broken rectangle.
- **Stamped symbols** are groups of primitives that mean one thing. A model
  should address the symbol, not redraw its anatomy.

These are shown as read-only geometry — id, bounding box, and for strokes a
simplified polyline — so the model can *align to* and *delete* them, which is
everything it legitimately needs. Elements of these types appearing in a patch
are dropped silently while the rest of the patch stands, because the client
still holds the real ones.

## The verbatim remainder

The tempting way to store elements is a column per interesting field. It is
also the way to lose data, because Excalidraw elements carry fields whose
purpose is not obvious and whose absence is not an error — it is a silent
behaviour change.

So storage extracts only what is worth querying and keeps the rest verbatim,
and reassembly treats the remainder as the arbiter. Three properties follow for
free, none of which require anyone to maintain a list:

- a field this package has never heard of round-trips untouched, including
  whatever a future Excalidraw release adds;
- a key the element never carried is not invented on the way back;
- a key the element explicitly set to null keeps its null.

That last one is why a null-valued field stays in the remainder rather than
being extracted to a NULL column: a NULL column cannot distinguish "the element
said null" from "the element never said it", and collapsing that difference is
exactly the silent damage this module exists to prevent.

## Deleted elements still own their files

Excalidraw keeps `isDeleted` elements in the array so undo can restore them.
Asset collection must therefore count deleted elements as references, or an
undo restores an image whose file has been swept — a broken image, produced by
a correct-looking garbage collector.

## Pure functions, no storage

Neither module touches a database, a filesystem, or a network. `explode()`
returns rows and `reassemble()` accepts them; the application owns its table,
its SQL, and its transaction.

This is a deliberate limit rather than an unfinished edge. A storage layer that
travels with the library forces every user onto one schema, one migration
style, and one connection discipline — and those are precisely the parts an
application already has opinions about. Pure functions compose with any of
them.

## Constants as keyword arguments

Every tuning value — the fields worth showing a model, which types are
read-only, the polyline budget, the coordinate bound — is a module constant
*and* a keyword default. An application that needs a different dialect passes
an argument. Nobody should have to fork a module to change a number.

## The corpus lives at the repository root

Not under `python/`. The fixtures are read by every language binding, and the
day one half of the library is fixed against a scene the other half cannot see
is the day the two halves start to disagree.
