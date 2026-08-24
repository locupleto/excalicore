# excalicore (TypeScript)

The browser half. Not yet written.

Some of the work an Excalidraw application does cannot happen on the server,
because it depends on what the canvas is about to render. Three pieces are the
same wherever that work is done, and belong here:

| Module | What it solves |
| --- | --- |
| `geometry` | Re-routing bound arrows centre-to-centre, and keeping labels legible when elements crowd. Excalidraw preserves whatever binding focus an arrow was first given, so an arrow created programmatically keeps a slant nobody asked for unless it is corrected. |
| `contrast` | Deciding whether a stroke colour is readable against the backgrounds it will actually sit on, and adjusting it when it is not. Palettes stay with the application; the perceptual maths does not. |
| `stamps` | Cloning a symbol from a library at a position, tagging the clones so they behave as one object, and sweeping the whole group when any of it is deleted. |

Tests will read `../corpus`, the same fixtures the Python suite uses. That is
why the corpus sits at the repository root: the day one half is fixed against a
scene the other half cannot see is the day the two halves start to disagree.
