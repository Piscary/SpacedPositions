// `when` expressions of commands (spec 02 §5): `view.list && selection.count > 0`, `!pane.pinned`, `panes > 1`.
// Same grammar as design/lib.py check_when. No eval.

const TOKEN = /\s*(?:(&&|\|\||==|!=|>=|<=|[!<>()])|('[^']*')|(\d+(?:\.\d+)?)|([A-Za-z_][\w.]*))/y
const cache = new Map()

function tokenize(expr) {
  const tokens = []
  TOKEN.lastIndex = 0
  while (TOKEN.lastIndex < expr.length) {
    const start = TOKEN.lastIndex
    const m = TOKEN.exec(expr)
    if (!m || TOKEN.lastIndex === start) {
      if (/^\s*$/.test(expr.slice(start))) break
      throw new Error(`can't read '${expr.slice(start)}'`)
    }
    if (m[1]) tokens.push({ op: m[1] })
    else if (m[2]) tokens.push({ value: m[2].slice(1, -1) })
    else if (m[3]) tokens.push({ value: Number(m[3]) })
    else tokens.push({ name: m[4] })
  }
  return tokens
}

function parse(expr) {
  const tokens = tokenize(expr)
  let i = 0
  const peek = () => tokens[i]?.op
  const primary = () => {
    const t = tokens[i++]
    if (!t) throw new Error("unexpected end")
    if (t.op === "!") { const inner = primary(); return (look) => !inner(look) }
    if (t.op === "(") {
      const inner = or()
      if (tokens[i++]?.op !== ")") throw new Error("missing )")
      return inner
    }
    if (t.op) throw new Error(`unexpected '${t.op}'`)
    if ("value" in t) return () => t.value
    return (look) => look(t.name)
  }
  const comparison = () => {
    const left = primary()
    const op = peek()
    if (["==", "!=", ">", "<", ">=", "<="].includes(op)) {
      i++
      const right = primary()
      return (look) => {
        const a = left(look), b = right(look)
        return { "==": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b }[op] // eslint-disable-line eqeqeq
      }
    }
    return left
  }
  const and = () => {
    let left = comparison()
    while (peek() === "&&") { i++; const l = left, r = comparison(); left = (look) => l(look) && r(look) }
    return left
  }
  const or = () => {
    let left = and()
    while (peek() === "||") { i++; const l = left, r = and(); left = (look) => l(look) || r(look) }
    return left
  }
  const fn = or()
  if (i !== tokens.length) throw new Error(`unexpected token at ${i}`)
  return fn
}

/** Evaluate `expr` with `look(name)` resolving identifiers. Empty expressions are true. */
export function evaluate(expr, look) {
  if (!expr) return true
  let fn = cache.get(expr)
  if (!fn) { fn = parse(expr); cache.set(expr, fn) }
  return Boolean(fn(look))
}
