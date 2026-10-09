import { helper as renamed, Worker } from '@/helpers'
import { leaf } from './leaf.js'
export function main(register: (fn: () => number) => void) {
  const callback = () => renamed()
  register(callback)
  new Worker().run()
  return leaf() + renamed()
}
export function recurse(n: number): number { return n ? recurse(n-1) : renamed() }
