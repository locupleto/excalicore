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
