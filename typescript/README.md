# excalicore (TypeScript)

The browser half. Some of the work an Excalidraw application does cannot
happen on the server, because it depends on what the canvas is about to
render. The pieces that are the same wherever that work is done belong here.

| Module | What it solves | State |
| --- | --- | --- |
| `stencils` | The contract a vocabulary element keeps so that arrows can bind to it, the application can find it again, and a language model can talk about it. Placing one, finding its subject's box again, sweeping it, restyling it. | written |
| `geometry` | Re-routing bound arrows centre-to-centre, and keeping labels legible when elements crowd. Excalidraw preserves whatever binding focus an arrow was first given, so an arrow created programmatically keeps a slant nobody asked for unless it is corrected. | planned |
| `contrast` | Deciding whether a stroke colour is readable against the backgrounds it will actually sit on, and adjusting it when it is not. Palettes stay with the application; the perceptual maths does not. | planned |

No runtime dependencies, no Excalidraw import, no DOM. Elements are plain
objects in whatever shape the application feeds its canvas — skeletons for
`convertToExcalidrawElements`, or full elements for `restoreElements` — and
come back in the same shape.

## `stencils`

A **stencil** is a named set of elements in which exactly one carries the
role `body` (a type an arrow can bind to) and the `frame` — the subject's box
relative to the body — at most one is the `label`, and everything else is a
`decoration` hung on the body by an anchor. An **instance** is a stencil
placed on a canvas: fresh ids, one shared group, and a `customData.stencil`
tag on every part beside whatever namespace the application writes.

```ts
import { fromLibraryItem, instantiate, frameOf, sweep } from 'excalicore/stencils'

const server = fromLibraryItem(libraryItem, { [headId]: 'body' })   // throws StencilError if invalid
const parts = instantiate(server, { x: 300, y: 200 })              // natural size
const store = instantiate(datastore, { x: 502, y: 202, width: 200, height: 76 }, {
  label: 'CMDB',
  variants: ['multiplicity'],
  tags: { bastion: { kind: 'component', key: 'cmdb' } },
  id: (source, role) => (role === 'body' ? 'c-cmdb' : `cp-cmdb-${source.id}`),
})
frameOf(store)            // → { x: 502, y: 202, width: 200, height: 76 }
sweep(board, ['g-c-cmdb']) // every part gone, arrows that bound to it unbound
```

| Function | Does |
| --- | --- |
| `validateStencil(elements)` | the contract, checked; violations come back as sentences |
| `fromLibraryItem(item, roles)` | an Excalidraw library item plus a role map becomes a stencil; the frame and the anchors are derived from the drawing when the map does not give them |
| `instantiate(stencil, at, options)` | places a stencil so that `frameOf()` gives `at` back; `fit` parts stretch with the subject, `fixed` parts keep their pixels; optional decorations are drawn only for the `variants` asked for |
| `frameOf(parts)` | the subject's box, from the body and its frame — the only way back |
| `bodyOf(parts)` | the one element an arrow may bind to |
| `instances(elements)` | every instance on a board, by id (the old `stampGroup` tag is read as an alias for one release) |
| `sweep(elements, ids)` | the board without those instances, bindings to them removed |
| `restyle(parts, style)` | the paint on the body, the tint on everything else |
| `bindToBodies(skeletons, board)` | arrows a model bound to an instance id, re-pointed at that instance's body |

The contract in full, and why it is shaped this way, is in `docs/design.md`.

## Tests

```
npm install && npm test     # at the repository root; node --test, no build step
npm run check               # tsc --noEmit
```

The `package.json` sits at the repository root — not under `typescript/` —
because npm can install a git dependency but not a subdirectory of one. An
application pins it by tag, as the Python half is pinned:

```
"excalicore": "git+ssh://git@github.com/locupleto/excalicore.git#v0.2.0"
```

The `prepare` script compiles `typescript/src` to `typescript/dist` on
install, which is what the package exports; Node refuses to strip types from
anything under `node_modules`, so the source cannot be exported as it is.

Tests read `../corpus`, the same fixtures the Python suite uses. That is why
the corpus sits at the repository root: the day one half is fixed against a
scene the other half cannot see is the day the two halves start to disagree.
`corpus/stencils/` holds the Bastion's four glyphs at their layout sizes, two
of the Armory's hand-drawn symbols as raw library items with role maps, and
the cases the validator must refuse.
