/**
 * Loading the shared golden corpus.
 *
 * The corpus sits at the repository root, not under a language, because the
 * Python and TypeScript halves must agree about the same scenes. A fixture
 * that only one half can read is how the two halves drift.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = new URL('../../corpus/', import.meta.url).pathname
export const SCENES = join(ROOT, 'scenes')
export const STENCILS = join(ROOT, 'stencils')
export const VOCABULARIES = join(ROOT, 'vocabularies')
export const GEOMETRY = join(ROOT, 'geometry')

function json(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'))
}

export function scene(name: string): { elements: Record<string, unknown>[] } {
  return json(join(SCENES, `${name}.json`)) as { elements: Record<string, unknown>[] }
}

export function elements(name: string): Record<string, unknown>[] {
  return scene(name).elements
}

export function stencilFixture(name: string): Record<string, unknown> {
  return json(join(STENCILS, `${name}.json`)) as Record<string, unknown>
}

export function stencilNames(): string[] {
  return readdirSync(STENCILS)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.slice(0, -5))
    .sort()
}

export function vocabularyFixture(name: string): Record<string, unknown> {
  return json(join(VOCABULARIES, `${name}.json`)) as Record<string, unknown>
}

/** The vocabulary documents themselves — `rejected` and `graphs` are cases
 *  and expectations, not vocabularies, and are excluded. */
export function vocabularyNames(): string[] {
  return readdirSync(VOCABULARIES)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.slice(0, -5))
    .filter((name) => name !== 'rejected' && name !== 'graphs')
    .sort()
}

/** One of `corpus/geometry/*.json` — each a `{doc, cases}` object, `doc`
 *  saying what shape its cases have so a reader (or the Python half) can
 *  understand the file without a TypeScript test alongside it. */
export function geometryFixture(name: string): { doc: string; cases: Record<string, unknown>[] } {
  return json(join(GEOMETRY, `${name}.json`)) as { doc: string; cases: Record<string, unknown>[] }
}
