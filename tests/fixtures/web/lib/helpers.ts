/** 返回加一后的值。 */
export function helper(value = 0) { return value + 1 }
export class Worker {
  constructor() { helper() }
  run() { return helper() }
}
