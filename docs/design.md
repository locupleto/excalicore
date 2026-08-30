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
- **Placed stencils** are groups of primitives that mean one thing. A model
  should address the symbol, not redraw its anatomy — and it may bind an
  arrow to it by the one id it is shown, which the client resolves to the
  stencil's body (`bindToBodies`).

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

## The stencil contract

Every Excalidraw application here draws a vocabulary — the Bastion's actor and
data store, the Armory's hand-drawn people and machines — and each did it
without a contract. The Bastion's glyph code carried one in disguise: a
"body" stamp on the one element that stands for a component, a way back from
that element to the component's box, a label that follows the model. The
Armory's stamps carried none, so its protocol had to tell the model *not to
bind arrows to a stamp*. That sentence is the cost of artwork without a
contract, and the reason the contract is here rather than in either
application.

**One body, and it is bindable.** A stick figure is five elements; an arrow
must bind to exactly one, and it must be a type Excalidraw can bind to. Naming
the body is what lets an arrow to a person mean something.

**The body carries the frame.** The way back from an element to what it
stands for is a stamp on the body — origin offset and size ratio — and nothing
else is ever read. Reading the geometry off whichever tagged part came last
is how an actor once walked down the sheet by its own height on every sync.

**Decorations are anchored, not scaled by a flag.** A glyph needs three
behaviours at once: limbs that grow with the figure, a ghost stack that keeps
a fixed pixel offset while matching the body's size, a caption that keeps its
size and pins to a point. A boolean cannot say that; an anchor in unit
coordinates, a pixel offset that never scales, and a `fit`/`fixed` size mode
can.

**Variants are decorations with a name.** Multiplicity draws two ghost
rectangles behind a box; it is not a different stencil. A decoration that
carries a `variant` is drawn only when the instantiation asks for it, which
keeps one stencil per kind and the choice with the model.

**The tag namespace is the library's; the subject is the application's.**
`customData.stencil` says what the part is; `customData.bastion` (or nothing
at all, for a sketch) says what it stands for. The library never reads the
second, which is how it can carry a kind without knowing what one means.

**Validated at load, never at draw.** A stencil with no body is an error with
a sentence, not a component that silently cannot be connected to.

**No shelf.** The library defines what a stencil must provide and validates
one; where stencils live, which one a view uses, and what a kind means stay
with the application.

## The vocabulary contract

Every application here has kinds — the Bastion's zone, actor, process,
datastore, external service and flow — and each declared its grammar in
code: which kind holds which, which may join which, self-loops allowed or
not. The Bastion carried it twice, once in Python and once in TypeScript,
and a third copy in a handful of `validate_deltas` predicates that the
docstring claimed covered containment cycles and did not. Two independent
copies of the same grammar are how a check drifts from its own docstring;
this contract is the fix, held once and checked the same way everywhere it
is used.

**A vocabulary is a document, not a switch statement.** A kind's role —
`node`, `container` or `connector` — decides what holds what and what joins
what; `within`, `placed`, `ends`, `directed`, `loops` and `parallel` are data
an application ships and a facilitator or a reviewer can read without
opening the source. Excalicore never holds a *particular* vocabulary, the
same way it never holds a particular stencil — it holds the shape a
vocabulary must have and checks whichever one it is handed.

**A graph is built after the patch, not before.** The application hands the
checker the graph it wants checked — for a delta, the graph *after* the
delta applies. Delete rules fall out for free this way: a zone deleted while
still holding a component leaves a subject sitting within something that is
no longer on the board, and a component deleted while still touched by a
flow leaves a connection with a missing end. No patch language enters the
library; it only ever sees a graph.

**Containment cycles are rule, not vigilance.** A zone whose parent is set by
an `update` op, or a `within` edited into a cycle, are the same shape as any
other malformed containment and get the same treatment: rule 11 and rule 12
run on every check, not on the operations an author remembered to guard.

**Suppression, not double jeopardy.** A subject with an unknown kind is
reported once for that, not again for the containment it can no longer be
meaningfully checked against; a connection missing an end is reported once
for that, not again for the end-kind, loop or parallel rules that need both
ends to mean anything. Each rule checks what the rule before it left
uncontradicted, which is why the rules are numbered and applied in the order
they are numbered.

**Sentences, not booleans.** `validate` and `check` return every violation as
a sentence, quoted and sorted where they name identifiers, so that the same
wording reaches a log, a facilitator's prompt and a corpus fixture without a
translation step in between.

**No STRIDE, no lint, no crossing rules.** What a connection crossing a
container boundary *means* — the Bastion's STRIDE arithmetic, its
`multi_boundary_hop` lint — is a rule about the graph's shape that the
application still owns. The vocabulary says a flow may run between any two
kinds; what running between two zones implies is not this module's
question.
