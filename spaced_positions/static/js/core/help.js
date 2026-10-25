// Help `?` (spec 04 · Help), over the focused pane, in three tabs: the pane's Guide (what it is for, how to do the
// usual things, what it works with), its Keys (every key that works right now, grouped by context, with a filter;
// `a` switches to all contexts) and Search (the query language). The guides come from the server
// (templates/help/<view>.html, in the language of the app); their keys are filled in from the keymap here, so a
// rebound key shows as the user has it.

import { command, enabled, handle, keymap, primaryKeys, run } from "./commands.js"
import { ctx, keycaps, setLayer } from "./context.js"
import { activeContexts, setOverlayHandler } from "./keys.js"
import { tr } from "./i18n.js"

const CONTEXT_LABELS = {
  global: tr("Everywhere"),
  pane: tr("Any pane"),
  "layer.insert": tr("In a text field (Insert)"),
  "view.list": tr("Lists"),
}
const TABS = [
  { id: "guide", label: tr("Guide") },
  { id: "keys", label: tr("Keys") },
  { id: "search", label: tr("Search") },
]
const guides = new Map() // topic → html, per page load (the language doesn't change without a reload)

let open = null
let lastTab = "guide"
try { lastTab = localStorage.getItem("spos.help.tab") || "guide" } catch { /* private window: the guide first */ }

function label(context) {
  if (CONTEXT_LABELS[context]) return CONTEXT_LABELS[context]
  const [kind, name] = context.split(".")
  if (kind === "view") return tr("View: {name}", { name: window.SPOS.views[name]?.label || name })
  if (kind === "mode") return tr("Mode: {name}", { name: window.SPOS.modes[name]?.label || name })
  return context
}

function renderKeys() {
  const contexts = open.all ? Object.keys(keymap()) : [...activeContexts(), "layer.insert"]
  const filter = open.filter.value.trim().toLowerCase()
  open.body.replaceChildren()
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
    open.body.append(group)
  }
  if (!open.body.children.length) open.body.append(Object.assign(document.createElement("p"), { className: "muted", textContent: tr("No key matches the filter") }))
  open.mode.textContent = open.all ? tr("all contexts · a: this context") : tr("this context · a: all contexts")
}

/** The user's keys in place of the defaults the server wrote into the guide. */
function fillKeys(root) {
  for (const el of root.querySelectorAll("[data-keys-for]")) {
    const args = el.dataset.keysArgs ? el.dataset.keysArgs.split(" ") : undefined
    const wanted = args ? args.join(" ") : null
    const local = Object.entries(keymap()[el.dataset.keysIn] || {})
      .find(([, b]) => b.command === el.dataset.keysFor && (wanted === null || b.args.join(" ") === wanted))
    const keys = local ? local[0].split(" ") : primaryKeys(el.dataset.keysFor, args)
    if (keys) el.replaceChildren(keycaps(keys))
  }
}

async function renderGuide(topic) {
  open.body.replaceChildren(Object.assign(document.createElement("p"), { className: "muted", textContent: tr("Loading…") }))
  if (!guides.has(topic)) {
    const html = await fetch(`/help/${topic}/`).then((r) => (r.ok ? r.text() : null)).catch(() => null)
    if (html === null) return open?.body.replaceChildren(Object.assign(document.createElement("p"), { className: "muted", textContent: tr("The guide could not be loaded") }))
    guides.set(topic, html)
  }
  if (!open || open.tab === "keys") return
  open.body.innerHTML = guides.get(topic)
  fillKeys(open.body)
}

function render() {
  for (const button of open.tabs.querySelectorAll("[data-tab]")) button.setAttribute("aria-checked", String(button.dataset.tab === open.tab))
  open.filter.hidden = open.tab !== "keys"
  open.mode.hidden = open.tab !== "keys"
  open.body.scrollTop = 0
  open.el.scrollTop = 0
  if (open.tab === "keys") return renderKeys()
  return renderGuide(open.tab === "search" ? "search" : open.view)
}

function setTab(tab) {
  open.tab = tab
  lastTab = tab
  try { localStorage.setItem("spos.help.tab", tab) } catch { /* not remembered: fine */ }
  render()
}

function show(tab = lastTab, { all = false } = {}) {
  close()
  const pane = ctx.pane?.el
  if (!pane) return false
  const el = document.createElement("div")
  el.className = "help"
  el.setAttribute("role", "dialog")
  const view = ctx.pane.view || "pane"
  el.setAttribute("aria-label", tr("Help: {name}", { name: window.SPOS.views[view]?.label || tr("Pane") }))
  const top = document.createElement("div")
  top.className = "help__top"
  const title = document.createElement("h2")
  title.textContent = window.SPOS.views[view]?.label || tr("Pane")
  const tabs = document.createElement("span")
  tabs.className = "segmented help__tabs"
  tabs.setAttribute("role", "radiogroup")
  tabs.setAttribute("aria-label", tr("Help"))
  const options = document.createElement("span")
  options.className = "segmented__options"
  TABS.forEach((t, i) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "segmented__option"
    button.setAttribute("role", "radio")
    button.dataset.tab = t.id
    button.append(t.label, " ", keycaps([String(i + 1)]))
    button.addEventListener("click", () => setTab(t.id))
    options.append(button)
  })
  tabs.append(options)
  const filter = document.createElement("input")
  filter.className = "field help__filter"
  filter.placeholder = tr("/ filter")
  filter.setAttribute("aria-label", tr("Filter the keys"))
  const mode = document.createElement("span")
  mode.className = "muted"
  const closer = document.createElement("span")
  closer.className = "help__close muted"
  closer.append(keycaps(["esc"]), " ", tr("close"), " · ", keycaps(["h"]), keycaps(["l"]), " ", tr("tabs"), " · ", keycaps(["j"]), keycaps(["k"]), " ", tr("scroll"))
  top.append(title, tabs, filter, mode, closer)
  const body = document.createElement("div")
  body.className = "help__body"
  el.append(top, body)
  pane.append(el)
  open = { el, filter, body, mode, tabs, all, tab, view, previous: ctx.layer }
  filter.addEventListener("input", () => renderKeys())
  ctx.overlay = "help"
  setOverlayHandler(onKey)
  render()
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
      return renderKeys()
    }
    if (typing) return open.filter.blur()
    return close()
  }
  if (typing) return "pass"
  const index = TABS.findIndex((t) => t.id === open.tab)
  if (["1", "2", "3"].includes(token)) return setTab(TABS[Number(token) - 1].id)
  if (token === "l" || token === "right") return setTab(TABS[(index + 1) % TABS.length].id)
  if (token === "h" || token === "left") return setTab(TABS[(index + TABS.length - 1) % TABS.length].id)
  if (token === "j" || token === "down") return open.el.scrollBy({ top: 48 })
  if (token === "k" || token === "up") return open.el.scrollBy({ top: -48 })
  if (token === "J" || token === "pagedown" || token === "space") return open.el.scrollBy({ top: open.el.clientHeight * 0.8 })
  if (token === "K" || token === "pageup") return open.el.scrollBy({ top: -open.el.clientHeight * 0.8 })
  if (token === "/") {
    if (open.tab !== "keys") setTab("keys")
    return open.filter.focus()
  }
  if (token === "a" && open.tab === "keys") {
    open.all = !open.all
    return renderKeys()
  }
  if (token === "?") return close()
  if (token === ":") {
    close()
    return run("cmdline.open")
  }
}

handle("help.context", () => show())
handle("help.all", () => show("keys", { all: true }))
handle("help.search", () => show("search"))
