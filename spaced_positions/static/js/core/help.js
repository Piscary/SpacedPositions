// Help `?` (spec 04 · Help): every key that works right now, over the focused pane, grouped by context, with a
// filter. `a` switches to all contexts.

import { command, enabled, handle, keymap, run } from "./commands.js"
import { ctx, keycaps, setLayer } from "./context.js"
import { activeContexts, setOverlayHandler } from "./keys.js"

const CONTEXT_LABELS = {
  global: "Everywhere",
  pane: "Any pane",
  "layer.insert": "In a text field (Insert)",
  "view.list": "Lists",
}

let open = null

function label(context) {
  if (CONTEXT_LABELS[context]) return CONTEXT_LABELS[context]
  const [kind, name] = context.split(".")
  if (kind === "view") return `View: ${window.SPOS.views[name]?.label || name}`
  if (kind === "mode") return `Mode: ${window.SPOS.modes[name]?.label || name}`
  return context
}

function render(all) {
  const contexts = all ? Object.keys(keymap()) : [...activeContexts(), "layer.insert"]
  const filter = open.filter.value.trim().toLowerCase()
  open.groups.replaceChildren()
  for (const context of contexts) {
    const bindings = Object.entries(keymap()[context] || {}).filter(([seq, b]) => {
      const spec = command(b.command)
      return !filter || `${seq} ${spec?.title} ${b.command}`.toLowerCase().includes(filter)
    })
    if (!bindings.length) continue
    const group = document.createElement("div")
    group.className = "help__group"
    const h = document.createElement("h3")
    h.textContent = label(context)
    const table = document.createElement("div")
    table.className = "help__table"
    for (const [seq, b] of bindings) {
      const spec = command(b.command)
      const title = document.createElement("span")
      title.textContent = (spec?.title || b.command) + (b.args.length ? ` ${b.args.join(" ")}` : "")
      if (!enabled(b.command).ok) title.className = "muted"
      const id = document.createElement("span")
      id.className = "help__id"
      id.textContent = b.command
      table.append(keycaps(seq), title, id)
    }
    group.append(h, table)
    open.groups.append(group)
  }
  open.mode.textContent = all ? "all contexts · a: this context" : "this context · a: all contexts"
}

function show(all = false) {
  close()
  const pane = ctx.pane?.el
  if (!pane) return false
  const el = document.createElement("div")
  el.className = "help"
  const top = document.createElement("div")
  top.className = "help__top"
  const title = document.createElement("h2")
  title.textContent = "Keys"
  const filter = document.createElement("input")
  filter.className = "field help__filter"
  filter.placeholder = "/ filter"
  const mode = document.createElement("span")
  mode.className = "muted"
  top.append(title, filter, mode, keycaps(["esc"]))
  const groups = document.createElement("div")
  el.append(top, groups)
  pane.append(el)
  open = { el, filter, groups, mode, all, previous: ctx.layer }
  filter.addEventListener("input", () => render(open.all))
  ctx.overlay = "help"
  setOverlayHandler(onKey)
  render(all)
}

function close() {
  if (!open) return
  open.el.remove()
  setLayer(open.previous === "pending" ? "normal" : open.previous)
  open = null
  ctx.overlay = null
  setOverlayHandler(null)
}

function onKey(e, token) {
  const typing = document.activeElement === open.filter
  if (token === "esc") {
    if (typing && open.filter.value) {
      open.filter.value = ""
      return render(open.all)
    }
    return close()
  }
  if (typing) return "pass"
  if (token === "/") return open.filter.focus()
  if (token === "a") {
    open.all = !open.all
    return render(open.all)
  }
  if (token === "?") return close()
  if (token === ":") {
    close()
    return run("cmdline.open")
  }
}

handle("help.context", () => show(false))
handle("help.all", () => show(true))
