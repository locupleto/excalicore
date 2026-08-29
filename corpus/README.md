# The corpus

Golden scenes and model replies, shared by every language binding in this
repository. It lives at the root rather than under `python/` because the Python
and TypeScript halves must agree about the same fixtures; a scene only one half
can read is how the two halves drift apart.

## Scenes (`scenes/*.json`)

| File | What it is for |
| --- | --- |
| `bound-labels.json` | A real editor export (Excalidraw 0.18.x): six labels bound to containers via `containerId` + `boundElements`, full bookkeeping fields, hand-placed arrows. |
| `arrow-bindings.json` | Arrows bound by `{elementId, focus, gap}` — including one binding pointing at an element that is no longer on the board. |
| `freedraw.json` | A 220-point hand stroke with pressures, well over the polyline budget. |
| `stamp-group.json` | Three primitives sharing `customData.stampGroup`, plus an unrelated neighbour that must not be swallowed. |
| `image-and-files.json` | An image with a `fileId`, a deleted image still holding its file, and a file no element references. |
| `stencil-instances.json` | Two stencil instances placed under the contract (an actor of five parts, a data store of four), a flow arrow bound to the data store's body, and a neighbour nothing owns. |

## Stencils (`stencils/*.json`)

Stencil definitions the TypeScript `stencils` module is fixed against.

| File | What it is for |
| --- | --- |
| `bastion-actor.json` | A stick figure at its layout size (120×128): the head is the body and carries the frame; limbs are `fit` decorations; the name is a `fixed` label pinned 18px above the subject's bottom edge. |
| `bastion-process.json`, `bastion-external-service.json` | A box (200×88) with a bound label; the external service is dashed. Both carry the multiplicity ghost stack as a `variant`. |
| `bastion-datastore.json` | The open-ended DFD store (200×76): the rectangle is the body, two rules are decorations anchored to its top and bottom edges. |
| `armory-stick-man.json`, `armory-server.json` | Two of the Armory's hand-drawn symbols as raw Excalidraw library items, plus the role map that makes them stencils — everything but the body is derived. |
| `rejected.json` | Definitions the validator must refuse, each with the reason: no body, two bodies, a body that cannot be bound to, a body without a frame, two labels, a label bound to a decoration, an untagged part. |

The Bastion fixtures mirror `the-bastion/frontend/src/render.ts` at the sizes
`backend/layout.py` produces, and the TypeScript tests check the placed
geometry against that renderer's formulas.

## Replies (`replies/*.txt`)

Model replies as they actually arrive: fenced and unfenced patches, two patches
in one message, prose with no patch, an echoed read-only stroke, a stencil
placement (and the same under its old name, `stamp`), and one patch whose second element is out of bounds — which must
reject the whole patch, never half of it.

## Adding to it

Add a fixture when a real board breaks something. A corpus grown from actual
failures is worth more than one grown from imagination, and every entry here
should be traceable to a case some application had to handle.

Never add a fixture containing anyone's private or confidential content.
These files are committed and travel with the repository; the boards they were
captured from do not. Neutralize the text before adding a captured scene — the
structure is what the fixture is for, and the words never are.
