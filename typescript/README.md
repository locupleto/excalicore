# excalicore (TypeScript) — not yet extracted

The browser half of the duplication, measured across the applications:

| Module | Lifted from | Evidence |
| --- | --- | --- |
| `geometry.ts` — `normalizeBoundArrows`, `topAlignCrowdedLabels` | `the-armory/frontend/src/pages/sketchGeometry.ts`, `the-academy/frontend/src/pages/boardGeometry.ts` | 379 lines; the two files differ on four lines, all inside comments |
| `contrast.ts` — `displayed`, `displayedContrast`, `readableInk` | `sketchColors.ts`, `chalkColors.ts` | the same four functions in both; the palettes around them are genuinely per-application and stay put |
| `stamps.ts` — clone with `stampGroup`, group-delete sweep | `Sketch.tsx`, `Board.tsx` | the same logic at four call sites |

These tests will read `../corpus`, the same fixtures the Python suite uses. That
is the point of putting the corpus at the repository root: the two halves must
agree about the same scenes, or they will drift apart the moment one of them is
fixed alone.
