// The context object (spec 02 §5), a tiny event bus and the status line.

export const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

export const ctx = {
  mode: "home",
  previousMode: null,
  layer: "normal", // normal | insert | pending | visual | command | hint
  overlay: null, // null | cmdline | help | menu | hint
  pane: null, // {id, view, n, group, pinned, sections, search}
  panes: 0,
  buffers: 0,
  selection: { count: 0 },
  theme: "",
  launched: false,
  undoDepth: 0,
  redoDepth: 0,
  lastRepeat: null,
  trainState: null, // launcher | solving | feedback | result (spec 04 · Train)
  prefersDark: matchMedia("(prefers-color-scheme: dark)").matches,
}

// `when` identifiers that aren't plain paths into ctx.
const derived = {
  "mode.hasPrevious": () => Boolean(ctx.previousMode),
  "undo.available": () => ctx.undoDepth > 0,
  "redo.available": () => ctx.redoDepth > 0,
  "repeat.available": () => Boolean(ctx.lastRepeat),
  "app.launched": () => ctx.launched,
  "pane.sections": () => Boolean(ctx.pane?.sections),
  "pane.search": () => Boolean(ctx.pane?.search),
  "pane.fields": () => Boolean(ctx.pane?.el?.querySelector(FIELDS)),
  "train.solving": () => ctx.mode === "train" && ctx.trainState === "solving",
  "train.running": () => ctx.mode === "train" && ["solving", "feedback"].includes(ctx.trainState),
  "train.hasLast": () => Boolean(window.SPOS?.train?.hasLast()),
  "train.hasMissed": () => Boolean(window.SPOS?.train?.hasMissed()),
  "analysis.loaded": () => ctx.mode === "analyse" && Boolean(window.SPOS?.analysis?.loaded()),
  "analysis.onMove": () => ctx.mode === "analyse" && Boolean(window.SPOS?.analysis?.onMove()),
  "analysis.hasList": () => ctx.mode === "analyse" && Boolean(window.SPOS?.analysis?.hasList()),
  "collect.hasDuplicate": () => ctx.mode === "collect" && Boolean(window.SPOS?.collect?.hasDuplicate()),
  "library.hasTarget": () => Boolean(window.SPOS?.library?.hasTarget()),
  "engine.ready": () => ctx.mode === "analyse" && Boolean(window.SPOS?.engine?.ready()),
}

export function lookup(name) {
  if (name in derived) return derived[name]()
  if (name.startsWith("view.")) return ctx.pane?.view === name.slice(5)
  if (name.startsWith("mode.")) return ctx.mode === name.slice(5)
  if (name.startsWith("layer.")) return ctx.layer === name.slice(6)
  return name.split(".").reduce((value, part) => (value == null ? undefined : value[part]), ctx)
}

/** Text fields a pane can be edited through (`i`). */
export const FIELDS = "input:not([type=hidden]):not([disabled]):not([type=button]):not([type=checkbox]):not([type=radio]), textarea:not([disabled]), select:not([disabled])"

const bus = new EventTarget()
export const on = (type, fn) => bus.addEventListener(type, (e) => fn(e.detail))
export const emit = (type, detail = {}) => bus.dispatchEvent(new CustomEvent(type, { detail }))

const $ = (id) => document.getElementById(id)
const LAYER_LABELS = { normal: "Normal", insert: "Insert", pending: "Pending", visual: "Visual", command: "Command", hint: "Hint" }

export function setLayer(layer) {
  if (ctx.layer === layer) return
  ctx.layer = layer
  $("shell").dataset.layer = layer
  $("status-layer").textContent = LAYER_LABELS[layer] || layer
  emit("layer", { layer })
}

let messageTimer
/** Show a message in the status line (spec 03 §1). kind: info | good | error | tip. */
export function status(text, { kind = "info", timeout = 6000, keys = null } = {}) {
  const el = $("status-message")
  el.dataset.kind = kind
  el.textContent = text
  if (keys) {
    const hint = document.createElement("span")
    hint.className = "muted"
    hint.append(" · ", keycaps(keys.seq), ` ${keys.label}`)
    el.append(hint)
  }
  clearTimeout(messageTimer)
  if (timeout) messageTimer = setTimeout(() => { el.textContent = ""; el.dataset.kind = "" }, timeout)
}

export function setActivity(text) {
  $("status-activity").textContent = text || ""
}

export function updateStatus() {
  $("status-mode").textContent = window.SPOS?.modes?.[ctx.mode]?.label || ctx.mode
  const pane = $("status-pane")
  pane.replaceChildren()
  if (ctx.pane) {
    const n = document.createElement("b")
    n.textContent = ctx.pane.n
    pane.append(n, ` ${window.SPOS?.views?.[ctx.pane.view]?.label || ctx.pane.view}`)
  }
  const subject = $("status-subject")
  subject.textContent = ctx.selection.count ? `${ctx.selection.count} selected` : ctx.pane?.subject || ""
}

// ── Key display (mirrors design/lib.py display_key) ─────────────────────────────────────────────────────────────
const DISPLAY = {
  space: "␣", enter: "↵", esc: "Esc", tab: "⇥", backspace: "⌫", delete: "⌦", up: "↑", down: "↓", left: "←",
  right: "→", home: "Home", end: "End", pageup: "PgUp", pagedown: "PgDn", shift: "⇧", alt: "⌥", ctrl: "Ctrl",
}

export function splitKey(token) {
  if (token === "+") return [[], "+"]
  if (token.endsWith("++")) return [token.slice(0, -2).split("+"), "+"]
  const parts = token.split("+")
  return [parts.slice(0, -1), parts[parts.length - 1]]
}

export function displayKey(token) {
  const [mods, key] = splitKey(token)
  const shown = mods.map((m) => (m === "mod" ? (isMac ? "⌘" : "Ctrl") : DISPLAY[m] || m))
  shown.push(DISPLAY[key] || (mods.length && /^[a-z]$/.test(key) ? key.toUpperCase() : key))
  return shown.join(isMac ? "" : "+")
}

/** <span class="keys"><kbd class="keycap">…</kbd>…</span> for a list of key tokens or a "space w v" string. */
export function keycaps(seq) {
  const tokens = Array.isArray(seq) ? seq : seq.split(" ")
  const wrap = document.createElement("span")
  wrap.className = "keys"
  for (const token of tokens) {
    const kbd = document.createElement("kbd")
    kbd.className = "keycap"
    kbd.textContent = displayKey(token)
    wrap.append(kbd)
  }
  return wrap
}

export function storage(key, value) {
  // Per-viewer conveniences only (command history); never needed for correctness.
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(`spos.${key}`) || "null")
    localStorage.setItem(`spos.${key}`, JSON.stringify(value))
  } catch {
    return null
  }
}
