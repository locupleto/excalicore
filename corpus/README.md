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

## Replies (`replies/*.txt`)

Model replies as they actually arrive: fenced and unfenced patches, two patches
in one message, prose with no patch, an echoed read-only stroke, a stamp
placement, and one patch whose second element is out of bounds — which must
reject the whole patch, never half of it.

## Adding to it

Add a fixture when a real board breaks something. A corpus grown from actual
failures is worth more than one grown from imagination, and every entry here
should be traceable to a case some application had to handle.

Never add a fixture containing content from a real engagement, lecture, or
private board. These files are committed; the boards they came from are not.
