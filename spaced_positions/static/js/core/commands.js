// Commands end to end (spec 02 §3, 09 §4): the registry, `when`, client and server handlers, button flash,
// teach-keys tips, undo/redo and repeat.

import { ctx, emit, keycaps, lookup, status } from "./context.js"
import { evaluate } from "./when.js"
import { tr } from "./i18n.js"

let registry = { commands: {}, keymap: {}, prefixes: {} }
const handlers = new Map()
const undoStack = []
const redoStack = []
const UNDO_LIMIT = 100

export function setRegistry(data) {
  registry = data
}
export const commands = () => registry.commands
export const keymap = () => registry.keymap
export const prefixes = () => registry.prefixes
export const command = (id) => registry.commands[id]

/** Register the client handler of a command: handle("pane.close", (args, meta) => …). */
export function handle(id, fn) {
  handlers.set(id, fn)
}

export function enabled(id) {
  const spec = registry.commands[id]
  if (!spec) return { ok: false, reason: tr("unknown command") }
  try {
    if (!evaluate(spec.when, lookup)) return { ok: false, reason: spec.reason || tr("not available here") }
  } catch (err) {
    return { ok: false, reason: `bad when: ${err.message}` }
  }
  return { ok: true }
}

/** The first binding of a command (key tokens), matching args when given. */
export function primaryKeys(id, args) {
  const wanted = args?.length ? args.join(" ") : null
  let fallback = null
  for (const bindings of Object.values(registry.keymap)) {
    for (const [seq, b] of Object.entries(bindings)) {
      if (b.command !== id) continue
      if (wanted === null || b.args.join(" ") === wanted) return seq.split(" ")
      fallback ??= seq.split(" ")
    }
  }
  return wanted === null ? null : fallback
}

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function serverContext() {
  return { mode: ctx.mode, theme: ctx.theme, prefersDark: ctx.prefersDark, pane: ctx.pane?.view || null }
}

/** POST /cmd/<id>/ and apply the result. Returns the JSON result, or null when it failed. */
// Server commands run one after another, in the order they were given: two quick changes of a setting must not
// reach the server (or come back) the other way round, which would leave the older value.
let queue = Promise.resolve()

export function serverRun(id, args, extra = {}) {
  const result = queue.then(() => sendCommand(id, args, extra))
  queue = result.catch(() => null)
  return result
}

async function sendCommand(id, args, extra) {
  let response
  try {
    response = await fetch(`/cmd/${id}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ args, context: serverContext(), ...extra }),
    })
  } catch {
    status(tr("{command}: the app is not reachable", { command: registry.commands[id]?.title }), { kind: "error" })
    return null
  }
  const result = await response.json().catch(() => ({ ok: false, message: `error ${response.status}` }))
  if (!result.ok) {
    status(result.message || "failed", { kind: "error" })
    return null
  }
  if (result.effects) emit("effects", result.effects)
  if (result.oob && window.htmx) window.htmx.swap(document.body, result.oob, { swapStyle: "none" })
  return result
}

/**
 * Run a command. source: what started it, "key" | "mouse" | "hint" | "cmdline" | "undo" | "repeat", or "code" when another
 * command or a module runs it (the usage report counts only what the user did).
 * Returns false if it didn't run.
 */
export async function run(id, args = [], { source = "code", silent = false } = {}) {
  const spec = registry.commands[id]
  if (!spec) {
    status(tr("unknown command '{id}'", { id }), { kind: "error" })
    return false
  }
  const state = enabled(id)
  if (!state.ok) {
    if (!silent) status(`${spec.title}: ${state.reason}`, { kind: "error" })
    return false
  }
  flash(id, args)
  if (source === "mouse") teach(id, args)

  if (spec.handler === "server") {
    const required = (spec.args || []).filter((a) => !a.optional).length
    if (args.length < required && spec.aliases?.length) {
      // a key or button without the value it needs: the command line asks for it, with completion
      const { openCmdline } = await import("./cmdline.js")
      return openCmdline(`${spec.aliases[0]} ${args.join(" ")}${args.length ? " " : ""}`)
    }
    const result = await serverRun(id, args)
    if (!result) return false
    if (!silent && result.message) {
      status(result.message, { kind: "good", keys: result.undo && source !== "undo" ? undoHint() : null })
    }
    if (result.undo && source !== "undo") {
      pushUndo({
        label: result.message || spec.title,
        undo: () => run(result.undo.command, result.undo.args, { source: "undo" }),
        redo: () => run(result.redo?.command || id, result.redo?.args || args, { source: "undo" }),
      })
    }
  } else {
    const fn = handlers.get(id)
    if (!fn) {
      status(tr("{command}: not implemented yet", { command: spec.title }), { kind: "error" })
      return false
    }
    const out = await fn(args, { source })
    if (out === false) return false
  }
  if (spec.repeatable && source !== "undo") {
    ctx.lastRepeat = { id, args }
  }
  emit("command", { id, args, source })
  return true
}

// ── Undo / redo / repeat ───────────────────────────────────────────────────────────────────────────────────────

/** entry: {label, undo: async fn, redo: async fn}. */
export function pushUndo(entry) {
  undoStack.push(entry)
  if (undoStack.length > UNDO_LIMIT) undoStack.shift()
  redoStack.length = 0
  syncDepth()
}

function syncDepth() {
  ctx.undoDepth = undoStack.length
  ctx.redoDepth = redoStack.length
}

const undoHint = () => ({ seq: primaryKeys("undo") || ["u"], label: tr("undo") })

handle("undo", async () => {
  const entry = undoStack.pop()
  if (!entry) return false
  await entry.undo()
  redoStack.push(entry)
  syncDepth()
  status(tr("Undone: {what}", { what: entry.label }), { keys: { seq: primaryKeys("redo") || ["U"], label: tr("redo") } })
})

handle("redo", async () => {
  const entry = redoStack.pop()
  if (!entry) return false
  await entry.redo()
  undoStack.push(entry)
  syncDepth()
  status(tr("Redone: {what}", { what: entry.label }), { keys: undoHint() })
})

handle("repeat", () => {
  const last = ctx.lastRepeat
  if (!last) return false
  return run(last.id, last.args, { source: "repeat" })
})

// ── Feedback: key flash and teach-keys ─────────────────────────────────────────────────────────────────────────

function flash(id, args) {
  const argText = args.join(" ")
  for (const el of document.querySelectorAll(`[data-cmd="${CSS.escape(id)}"]`)) {
    if ((el.dataset.args || "") !== argText && el.dataset.args) continue
    if (!el.offsetParent) continue
    el.classList.remove("is-flash")
    void el.offsetWidth // restart the transition
    el.classList.add("is-flash")
    setTimeout(() => el.classList.remove("is-flash"), 150)
  }
}

let teachKeys = true
export const setTeachKeys = (value) => { teachKeys = value }

function teach(id, args) {
  if (!teachKeys) return
  const keys = primaryKeys(id, args)
  if (!keys) return
  const el = document.getElementById("status-message")
  status(tr("tip: "), { kind: "tip", timeout: 4000 })
  el.append(keycaps(keys), ` ${registry.commands[id].title.toLowerCase()}`)
}

// ── Clicks on [data-cmd] run their command, the same path as keys ──────────────────────────────────────────────

document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-cmd]")
  if (!el || el.closest("[aria-disabled='true']")) return
  event.preventDefault()
  const args = el.dataset.args ? el.dataset.args.split(" ") : []
  run(el.dataset.cmd, args, { source: ctx.viaHint ? "hint" : "mouse" })
})
