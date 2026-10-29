// Workspaces, panes and splits (spec 03): the layout tree of each mode, focus, gutters, maximise/collapse, link
// groups, hidden buffers, persistence, mode switching. Pane contents are server-rendered fragments (/v/<view>/);
// this module only arranges them and never renders view HTML itself.

import { ctx, emit, setLayer, status, storage, updateStatus } from "./context.js"
import { command, enabled, handle, primaryKeys, pushUndo, run, serverRun } from "./commands.js"
import { openMenu } from "./menu.js"
import { tr } from "./i18n.js"

const workspaces = new Map() // mode → ws
const recent = [] // modes, most recent last: at most KEEP_ALIVE stay in the DOM (spec 03 §6)
const KEEP_ALIVE = 3
const gutterInfo = new WeakMap()
const SNAPS = [25, 100 / 3, 50, 200 / 3, 75]
const MIN_SHARE = 0.06

export const current = () => workspaces.get(ctx.mode)

// ── Tree helpers ───────────────────────────────────────────────────────────────────────────────────────────────

function panesOf(node, out = []) {
  if (node.type === "pane") out.push(node)
  else node.children.forEach((c) => panesOf(c, out))
  return out
}

/** {node, parent, index, path:[ancestors…]} of the node with this pane id. */
function find(node, id, parent = null, index = 0, path = []) {
  if (node.type === "pane") return node.id === id ? { node, parent, index, path } : null
  for (let i = 0; i < node.children.length; i++) {
    const hit = find(node.children[i], id, node, i, [...path, { split: node, index: i }])
    if (hit) return hit
  }
  return null
}

function replaceNode(ws, hit, replacement) {
  if (hit.parent) hit.parent.children[hit.index] = replacement
  else ws.tree = replacement
}

function newId(ws) {
  const used = [...panesOf(ws.tree), ...ws.buffers].map((p) => Number(p.id.slice(1)) || 0)
  for (const id of ws.els.keys()) used.push(Number(id.slice(1)) || 0)
  return `p${Math.max(0, ...used) + 1}`
}

function fail(message, options = { kind: "error" }) {
  status(message, options)
  return false
}

const clone = (value) => JSON.parse(JSON.stringify(value))
const snapshot = (ws) => clone({ tree: ws.tree, focus: ws.focus, buffers: ws.buffers, max: ws.max })

function restore(ws, snap) {
  Object.assign(ws, clone(snap))
  render(ws)
}

/** Change the layout through `mutate`, render, persist and push one undo step. */
function change(ws, label, mutate) {
  const before = snapshot(ws)
  if (mutate() === false) return false
  render(ws)
  const after = snapshot(ws)
  pushUndo({ label, undo: () => restore(ws, before), redo: () => restore(ws, after) })
}

// ── Rendering ──────────────────────────────────────────────────────────────────────────────────────────────────

function div(className) {
  const el = document.createElement("div")
  el.className = className
  return el
}

function buildNode(ws, node) {
  if (node.type === "pane") return paneEl(ws, node)
  const el = div(`split split--${node.dir}`)
  node.children.forEach((child, i) => {
    if (i) {
      const gutter = div("gutter")
      gutter.dataset.gutter = ""
      gutterInfo.set(gutter, { node, index: i })
      el.append(gutter)
    }
    const wrap = div("split__child")
    wrap.classList.toggle("is-collapsed", child.type === "pane" && child.collapsed)
    wrap.style.flex = `${node.sizes[i]} 1 0`
    wrap.append(buildNode(ws, child))
    el.append(wrap)
  })
  return el
}

function paneEl(ws, node) {
  const existing = ws.els.get(node.id)
  if (existing && existing.dataset.view === node.view) return existing
  const el = document.createElement("section")
  el.className = "pane"
  el.dataset.pane = node.id
  el.dataset.view = node.view
  const header = div("pane__header")
  const n = Object.assign(document.createElement("span"), { className: "pane__n" })
  n.dataset.paneN = ""
  const title = Object.assign(document.createElement("span"), { className: "pane__title" })
  title.textContent = window.SPOS.views[node.view]?.label || node.view
  header.append(n, title)
  el.append(header, div("pane__body"), div("pane__loading"))
  ws.els.set(node.id, el)
  loadPane(ws, node, el)
  return el
}

async function loadPane(ws, node, el) {
  const params = new URLSearchParams({
    pane: node.id, n: node.n || 0, group: node.group || "", pinned: node.pinned ? "1" : "", mode: ws.mode,
  })
  let html
  try {
    html = await fetch(`/v/${node.view}/?${params}`).then((r) => (r.ok ? r.text() : Promise.reject(r.status)))
  } catch (err) {
    el.querySelector(".pane__loading")?.remove()
    el.querySelector(".pane__body").textContent = tr("Could not load this view ({error}).", { error: err })
    return
  }
  const template = document.createElement("template")
  template.innerHTML = html.trim()
  const fresh = template.content.firstElementChild
  if (ws.els.get(node.id) !== el) return // replaced again meanwhile
  el.replaceWith(fresh)
  ws.els.set(node.id, fresh)
  window.htmx?.process(fresh)
  const live = find(ws.tree, node.id)?.node || ws.buffers.find((b) => b.id === node.id)
  if (live) decorate(ws, live)
  applyFocus(ws)
  emit("pane:load", { el: fresh, node: live || node })
}

/** Number, collapsed state, link badge and (when maximised) tabs of other panes in a pane's header. */
function decorate(ws, node) {
  const el = ws.els.get(node.id)
  if (!el) return
  const n = el.querySelector("[data-pane-n]")
  if (n) n.textContent = node.n
  el.classList.toggle("is-collapsed", Boolean(node.collapsed) && ws.max !== node.id)
  const link = el.querySelector("[data-pane-link]")
  if (link) {
    link.hidden = !node.group && !node.pinned
    link.textContent = node.pinned ? "⊙ pinned" : `⛓ ${node.group || ""}`
    if (node.group && !node.pinned) link.dataset.group = node.group
    else delete link.dataset.group
    link.dataset.cmd = "pane.group"
    link.title = tr("Link group: click to cycle")
  }
  const tabs = el.querySelector("[data-pane-tabs]")
  if (tabs) {
    tabs.replaceChildren()
    if (ws.max === node.id) {
      for (const other of panesOf(ws.tree)) {
        if (other.id === node.id) continue
        const tab = document.createElement("button")
        tab.type = "button"
        tab.className = "pane__tab"
        tab.dataset.cmd = "pane.focus"
        tab.dataset.args = String(other.n)
        tab.textContent = `${other.n} ${window.SPOS.views[other.view]?.label || other.view}`
        tabs.append(tab)
      }
    }
  }
}

function render(ws, { persist = true } = {}) {
  const scrolls = new Map()
  for (const [id, el] of ws.els) {
    const body = el.querySelector(".pane__body")
    if (body?.scrollTop) scrolls.set(id, body.scrollTop)
  }
  const panes = panesOf(ws.tree)
  panes.forEach((p, i) => { p.n = i + 1 })
  if (!panes.some((p) => p.id === ws.focus)) ws.focus = panes[0].id
  if (ws.max && !panes.some((p) => p.id === ws.max)) ws.max = null
  const root = ws.max ? paneEl(ws, panes.find((p) => p.id === ws.max)) : buildNode(ws, ws.tree)
  ws.el.replaceChildren(...ws.el.querySelectorAll(":scope > script"), root)
  panes.forEach((p) => decorate(ws, p))
  for (const [id, top] of scrolls) {
    const body = ws.els.get(id)?.querySelector(".pane__body")
    if (body) body.scrollTop = top
  }
  applyFocus(ws)
  if (persist) save(ws)
  emit("layout", { mode: ws.mode, el: ws.el })
}

/** The layout node of a pane element (its view, link group, pinned state). */
export function nodeOf(paneEl) {
  const ws = workspaces.get(paneEl.closest(".workspace")?.dataset.mode)
  if (!ws) return null
  const id = paneEl.dataset.pane
  return find(ws.tree, id)?.node || ws.buffers.find((b) => b.id === id) || null
}

function paneInfo(ws, node) {
  const el = ws.els.get(node.id)
  return {
    id: node.id,
    view: node.view,
    n: node.n,
    group: node.pinned ? null : node.group,
    pinned: Boolean(node.pinned),
    collapsed: Boolean(node.collapsed),
    sections: Boolean(el?.querySelector("[data-section]")),
    search: Boolean(el?.querySelector("[data-search]")),
    el,
  }
}

function applyFocus(ws) {
  if (ws.mode !== ctx.mode) return
  const panes = panesOf(ws.tree)
  const node = panes.find((p) => p.id === ws.focus) || panes[0]
  for (const [id, el] of ws.els) el.classList.toggle("is-focused", id === node.id)
  const before = ctx.pane?.el
  ctx.pane = paneInfo(ws, node)
  ctx.panes = panes.length
  ctx.buffers = ws.buffers.length
  const active = document.activeElement
  if (active && active !== document.body && !ctx.pane.el?.contains(active) && ws.el.contains(active)) active.blur()
  if (before !== ctx.pane.el) emit("focus", { pane: ctx.pane })
  updateStatus()
}

export function focusPane(id) {
  const ws = current()
  if (!ws || !find(ws.tree, id)) return
  ws.focus = id
  if (ws.max) ws.max = id
  if (ws.max) render(ws)
  else {
    applyFocus(ws)
    save(ws)
  }
}

// ── Persistence ────────────────────────────────────────────────────────────────────────────────────────────────

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function save(ws) {
  clearTimeout(ws.saveTimer)
  ws.saveTimer = setTimeout(() => {
    const strip = (node) =>
      node.type === "pane"
        ? { type: "pane", id: node.id, view: node.view, group: node.group || null, pinned: Boolean(node.pinned), collapsed: Boolean(node.collapsed) }
        : { type: "split", dir: node.dir, sizes: node.sizes.map((s) => Math.round(s * 100) / 100), children: node.children.map(strip) }
    fetch(`/state/${ws.mode}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ layout: strip(ws.tree), focus: ws.focus }),
    }).catch(() => status(tr("layout not saved: the app is not reachable"), { kind: "error" }))
  }, 500)
}

// ── Workspaces and modes ───────────────────────────────────────────────────────────────────────────────────────

export function initWorkspace(el) {
  const mode = el.dataset.mode
  const ws = {
    mode,
    el,
    tree: JSON.parse(el.querySelector(`:scope > script#layout-${mode}`).textContent),
    focus: el.dataset.focus,
    max: null,
    buffers: [],
    els: new Map(),
  }
  for (const pane of el.querySelectorAll("[data-pane]")) ws.els.set(pane.dataset.pane, pane)
  workspaces.set(mode, ws)
  touch(mode)
  el.addEventListener("pointerdown", (e) => onPointerDown(ws, e))
  el.addEventListener("contextmenu", (e) => onContextMenu(ws, e))
  emit("workspace", { mode, el })
  render(ws, { persist: false })
  return ws
}

function touch(mode) {
  const i = recent.indexOf(mode)
  if (i >= 0) recent.splice(i, 1)
  recent.push(mode)
  while (recent.length > KEEP_ALIVE) {
    // never the one on screen, nor one that holds work in progress (data-keep: a running training session)
    const index = recent.findIndex((m) => m !== ctx.mode && m !== mode && !workspaces.get(m)?.el.dataset.keep)
    if (index < 0) break
    const [old] = recent.splice(index, 1)
    workspaces.get(old)?.el.remove()
    workspaces.delete(old)
  }
}

let switchTicket = 0
const loading = new Map() // mode → promise of its workspace, so a mode is fetched once even if keys repeat

// Prefetch (spec 09 · speed): hovering a mode tab or pressing ␣ fetches the workspaces not loaded yet, so the switch
// that likely follows needs no request. Only the HTML is kept (a minute); the workspace is built on the switch.
const prefetched = new Map() // mode → {at, html: Promise<string>}
const PREFETCH_MS = 60_000

function prefetch(mode) {
  if (!window.SPOS.modes[mode] || workspaces.has(mode) || loading.has(mode)) return
  const known = prefetched.get(mode)
  if (known && performance.now() - known.at < PREFETCH_MS) return
  prefetched.set(mode, { at: performance.now(), html: fetch(`/m/${mode}/`).then((r) => (r.ok ? r.text() : Promise.reject(r.status))) })
}

function takePrefetched(mode) {
  const known = prefetched.get(mode)
  prefetched.delete(mode)
  return known && performance.now() - known.at < PREFETCH_MS ? known.html.catch(() => null) : Promise.resolve(null)
}

document.addEventListener("pointerover", (e) => {
  const tab = e.target.closest?.("[data-mode-tab]")
  if (tab) prefetch(tab.dataset.modeTab)
})
document.addEventListener("keydown", (e) => {
  if (e.key !== " " || ctx.layer !== "normal" || e.target.closest?.("input, textarea, select, [contenteditable]")) return
  for (const mode of Object.keys(window.SPOS.modes)) if (mode !== "ui") prefetch(mode) // ␣ leads to the mode keys
}, true)

function loadWorkspace(mode) {
  if (!loading.has(mode)) {
    loading.set(
      mode,
      takePrefetched(mode)
        .then((html) => html ?? fetch(`/m/${mode}/`).then((r) => r.text()))
        .then((html) => {
          const template = document.createElement("template")
          template.innerHTML = html.trim()
          const el = template.content.firstElementChild
          el.hidden = true
          document.getElementById("workspaces").append(el)
          window.htmx?.process(el)
          return initWorkspace(el)
        })
        .finally(() => loading.delete(mode)),
    )
  }
  return loading.get(mode)
}

export async function switchMode(mode, { push = true } = {}) {
  if (!window.SPOS.modes[mode]) return fail(tr("no mode '{name}'", { name: mode }))
  const ticket = ++switchTicket // fast keys: only the last requested mode becomes active
  if (mode === ctx.mode) return
  let ws = workspaces.get(mode)
  if (!ws) ws = await loadWorkspace(mode)
  else touch(mode)
  if (ticket !== switchTicket) return
  ctx.previousMode = ctx.mode
  ctx.mode = mode
  for (const other of workspaces.values()) other.el.hidden = other.mode !== mode
  for (const tab of document.querySelectorAll("[data-mode-tab]")) tab.classList.toggle("is-active", tab.dataset.modeTab === mode)
  document.title = `${window.SPOS.modes[mode].label} · Spaced Positions`
  if (ctx.layer === "visual") setLayer("normal")
  applyFocus(ws)
  if (push) history.pushState({ mode }, "", `/${mode}/`)
  emit("mode", { mode })
}

// ── Mouse: focus, gutters, context menu ────────────────────────────────────────────────────────────────────────

function onPointerDown(ws, e) {
  const gutter = e.target.closest("[data-gutter]")
  if (gutter) return startDrag(ws, gutter, e)
  const pane = e.target.closest("[data-pane]")
  if (pane && pane.dataset.pane !== ws.focus) focusPane(pane.dataset.pane)
}

function startDrag(ws, gutter, e) {
  const info = gutterInfo.get(gutter)
  if (!info) return
  e.preventDefault()
  const { node, index } = info
  const splitEl = gutter.parentElement
  const wraps = [...splitEl.children].filter((c) => c.classList.contains("split__child"))
  const row = node.dir === "row"
  const total = node.sizes.reduce((a, b) => a + b, 0)
  const before = node.sizes.slice(0, index - 1).reduce((a, b) => a + b, 0)
  const pair = node.sizes[index - 1] + node.sizes[index]
  const snap = snapshot(ws)
  gutter.setPointerCapture(e.pointerId)
  gutter.classList.add("is-dragging")
  document.body.classList.add("is-resizing")
  const move = (ev) => {
    const rect = splitEl.getBoundingClientRect()
    const frac = row ? (ev.clientX - rect.left) / rect.width : (ev.clientY - rect.top) / rect.height
    let pos = frac * total
    for (const s of SNAPS) if (Math.abs(frac * 100 - s) < 1.5) pos = (s / 100) * total
    const min = total * MIN_SHARE
    pos = Math.min(Math.max(pos, before + min), before + pair - min)
    node.sizes[index - 1] = pos - before
    node.sizes[index] = pair - (pos - before)
    wraps[index - 1].style.flex = `${node.sizes[index - 1]} 1 0`
    wraps[index].style.flex = `${node.sizes[index]} 1 0`
  }
  const up = () => {
    gutter.removeEventListener("pointermove", move)
    gutter.classList.remove("is-dragging")
    document.body.classList.remove("is-resizing")
    const after = snapshot(ws)
    if (JSON.stringify(after.tree) !== JSON.stringify(snap.tree)) {
      pushUndo({ label: tr("Resize"), undo: () => restore(ws, snap), redo: () => restore(ws, after) })
      save(ws)
    }
  }
  gutter.addEventListener("pointermove", move)
  gutter.addEventListener("pointerup", up, { once: true })
  gutter.addEventListener("pointercancel", up, { once: true })
}

function onContextMenu(ws, e) {
  const header = e.target.closest(".pane__header")
  if (!header) return
  e.preventDefault()
  const pane = header.closest("[data-pane]")
  focusPane(pane.dataset.pane)
  const ids = [
    "pane.view", "pane.split.vertical", "pane.split.horizontal", "pane.maximize", "pane.collapse",
    "pane.group", "pane.pin", "pane.swap", "pane.close",
  ]
  openMenu({
      title: tr("Pane"),
      anchor: { x: e.clientX, y: e.clientY },
      items: ids.map((id, i) => ({
        label: command(id).title,
        keys: primaryKeys(id),
        key: String(i + 1),
        note: enabled(id).ok ? "" : enabled(id).reason,
        disabled: !enabled(id).ok,
        value: id,
      })),
  }).then((choice) => choice && run(choice, [], { source: "mouse" }))
}

// ── View picker ────────────────────────────────────────────────────────────────────────────────────────────────

export function pickView(title = tr("View")) {
  const items = Object.entries(window.SPOS.views)
    .filter(([, v]) => v.picker)
    .map(([key, v]) => ({ label: v.label, key: v.picker, keys: [v.picker], value: key }))
  return openMenu({ title, items, anchor: ctx.pane?.el?.querySelector(".pane__header") })
}

async function viewArg(args, title) {
  if (args[0]) {
    if (!window.SPOS.views[args[0]]) {
      status(tr("no view '{name}'", { name: args[0] }), { kind: "error" })
      return null
    }
    return args[0]
  }
  return pickView(title)
}

// ── Commands ───────────────────────────────────────────────────────────────────────────────────────────────────

handle("mode.home", () => switchMode("home"))
handle("mode.train", () => switchMode("train"))
handle("mode.analyse", () => switchMode("analyse"))
handle("mode.collect", () => switchMode("collect"))
handle("mode.library", () => switchMode("library"))
handle("mode.stats", () => switchMode("stats"))
handle("mode.settings", () => switchMode("settings"))
handle("mode.ui", () => switchMode("ui"))
handle("mode.previous", () => switchMode(ctx.previousMode))

function focusedHit(ws = current()) {
  return find(ws.tree, ws.focus)
}

function cycleFocus(step) {
  const ws = current()
  const panes = panesOf(ws.tree)
  const i = panes.findIndex((p) => p.id === ws.focus)
  focusPane(panes[(i + step + panes.length) % panes.length].id)
}
handle("pane.focus.next", () => cycleFocus(1))
handle("pane.focus.prev", () => cycleFocus(-1))
handle("pane.focus", ([n]) => {
  const pane = panesOf(current().tree)[Number(n) - 1]
  if (!pane) return fail(tr("no pane {n}", { n }), { kind: "error" })
  focusPane(pane.id)
})
handle("pane.focus.dir", ([dir]) => {
  const ws = current()
  const from = ws.els.get(ws.focus)?.getBoundingClientRect()
  if (!from) return false
  const cx = from.left + from.width / 2, cy = from.top + from.height / 2
  let best = null
  for (const pane of panesOf(ws.tree)) {
    if (pane.id === ws.focus) continue
    const r = ws.els.get(pane.id)?.getBoundingClientRect()
    if (!r) continue
    const ok = { left: r.right <= from.left + 2, right: r.left >= from.right - 2, up: r.bottom <= from.top + 2, down: r.top >= from.bottom - 2 }[dir]
    if (!ok) continue
    const overlap = dir === "left" || dir === "right" ? Math.min(r.bottom, from.bottom) - Math.max(r.top, from.top) : Math.min(r.right, from.right) - Math.max(r.left, from.left)
    const dist = Math.hypot(r.left + r.width / 2 - cx, r.top + r.height / 2 - cy) - Math.max(0, overlap)
    if (!best || dist < best.dist) best = { id: pane.id, dist }
  }
  if (!best) return fail(tr("no pane in that direction"), { timeout: 2000 })
  focusPane(best.id)
})

async function split(dir, args) {
  const view = await viewArg(args, dir === "row" ? tr("Split: view of the new pane") : tr("Split below: view of the new pane"))
  if (!view) return false
  const ws = current()
  return change(ws, tr("Split"), () => {
    const hit = focusedHit(ws)
    const fresh = { type: "pane", id: newId(ws), view, group: hit.node.group || null, pinned: false, collapsed: false }
    if (hit.parent && hit.parent.dir === dir) {
      const half = hit.parent.sizes[hit.index] / 2
      hit.parent.sizes.splice(hit.index, 1, half, half)
      hit.parent.children.splice(hit.index + 1, 0, fresh)
    } else {
      replaceNode(ws, hit, { type: "split", dir, sizes: [50, 50], children: [hit.node, fresh] })
    }
    ws.focus = fresh.id
    ws.max = null
  })
}
/** A board and a move tree to the right of the focused pane, in a link group of their own (`o` in lists: open in a
 *  split). An earlier one is reused. Resolves with the group's letter once the panes are on screen. */
export async function openBeside() {
  const ws = current()
  const used = new Set(panesOf(ws.tree).map((p) => p.group).filter(Boolean))
  const mine = panesOf(ws.tree).find((p) => p.view === "moves" && p.group)
  if (mine) return mine.group
  const group = [..."BCDEFGH"].find((g) => !used.has(g)) || "H"
  await change(ws, tr("Open in a split"), () => {
    const hit = focusedHit(ws)
    const n = Number(newId(ws).slice(1))
    const pane = (view, id) => ({ type: "pane", id, view, group, pinned: false, collapsed: false })
    const board = pane("board", `p${n}`)
    const moves = pane("moves", `p${n + 1}`)
    const fresh = { type: "split", dir: "col", sizes: [62, 38], children: [board, moves] }
    if (hit.parent && hit.parent.dir === "row") {
      const half = hit.parent.sizes[hit.index] / 2
      hit.parent.sizes.splice(hit.index, 1, half, half)
      hit.parent.children.splice(hit.index + 1, 0, fresh)
    } else {
      replaceNode(ws, hit, { type: "split", dir: "row", sizes: [50, 50], children: [hit.node, fresh] })
    }
    ws.max = null
  })
  return group
}

/** Close what openBeside opened (Train: before the next puzzle), without an undo step. */
export function closeBeside() {
  const ws = current()
  const opened = panesOf(ws.tree).filter((p) => p.group && ["moves", "board"].includes(p.view) && panesOf(ws.tree).some((m) => m.view === "moves" && m.group === p.group))
  if (!opened.length) return false
  const focus = ws.focus
  for (const pane of opened) {
    ws.focus = pane.id
    removeFocused(ws)
  }
  ws.focus = panesOf(ws.tree).some((p) => p.id === focus) ? focus : panesOf(ws.tree)[0].id
  render(ws)
  return true
}

handle("pane.split.vertical", (args) => split("row", args))
handle("pane.split.horizontal", (args) => split("col", args))

function removeFocused(ws) {
  const hit = focusedHit(ws)
  if (!hit.parent) return false
  hit.parent.children.splice(hit.index, 1)
  hit.parent.sizes.splice(hit.index, 1)
  const sibling = hit.parent.children[Math.max(0, hit.index - 1)]
  if (hit.parent.children.length === 1) {
    const parentHit = hit.path.length > 1 ? { parent: hit.path[hit.path.length - 2].split, index: hit.path[hit.path.length - 2].index } : { parent: null }
    replaceNode(ws, parentHit, hit.parent.children[0])
  }
  ws.focus = panesOf(sibling)[0].id
  return hit.node
}

handle("pane.close", () => change(current(), tr("Close pane"), () => (removeFocused(current()) ? undefined : false)))

handle("pane.only", () => {
  const ws = current()
  return change(ws, tr("Only this pane"), () => {
    const hit = focusedHit(ws)
    ws.buffers.push(...panesOf(ws.tree).filter((p) => p.id !== hit.node.id))
    ws.tree = hit.node
    ws.max = null
  })
})

handle("pane.buffers", async () => {
  const ws = current()
  const choice = await openMenu({
    title: tr("Hidden buffers"),
    anchor: ctx.pane?.el?.querySelector(".pane__header"),
    items: ws.buffers.map((b, i) => ({ label: window.SPOS.views[b.view]?.label || b.view, key: String(i + 1), keys: [String(i + 1)], note: b.id, value: b.id })),
  })
  if (choice) return run("pane.buffer", [choice])
  return false
})

handle("pane.buffer", ([id]) => {
  const ws = current()
  const index = ws.buffers.findIndex((b) => b.id === id || b.view === id)
  if (index < 0) return fail(tr("no hidden buffer '{id}'", { id }), { kind: "error" })
  return change(ws, tr("Show buffer"), () => {
    const [node] = ws.buffers.splice(index, 1)
    const hit = focusedHit(ws)
    replaceNode(ws, hit, { type: "split", dir: "row", sizes: [50, 50], children: [hit.node, node] })
    ws.focus = node.id
  })
})

handle("pane.view", async (args) => {
  const view = await viewArg(args, tr("Change view"))
  if (!view) return false
  const ws = current()
  return change(ws, tr("Change view"), () => {
    focusedHit(ws).node.view = view
  })
})

handle("pane.maximize", () => {
  const ws = current()
  ws.max = ws.max ? null : ws.focus
  render(ws, { persist: false })
  status(ws.max ? tr("Maximised · the other panes are tabs in its header") : tr("Restored"), { timeout: 2500 })
})

handle("pane.collapse", () => {
  const ws = current()
  return change(ws, tr("Collapse"), () => {
    const node = focusedHit(ws).node
    node.collapsed = !node.collapsed
  })
})

handle("pane.swap", () => {
  const ws = current()
  return change(ws, tr("Swap panes"), () => {
    const panes = panesOf(ws.tree)
    const i = panes.findIndex((p) => p.id === ws.focus)
    const a = find(ws.tree, panes[i].id)
    const b = find(ws.tree, panes[(i + 1) % panes.length].id)
    a.parent.children[a.index] = b.node
    b.parent.children[b.index] = a.node
  })
})

handle("pane.rotate", () => {
  const ws = current()
  return change(ws, tr("Rotate split"), () => {
    const hit = focusedHit(ws)
    hit.parent.dir = hit.parent.dir === "row" ? "col" : "row"
  })
})

handle("pane.equalize", () => {
  const ws = current()
  return change(ws, tr("Equal sizes"), () => {
    const walk = (node) => {
      if (node.type !== "split") return
      node.sizes = node.children.map(() => 100 / node.children.length)
      node.children.forEach(walk)
    }
    walk(ws.tree)
  })
})

handle("pane.resize", ([dir]) => {
  const ws = current()
  const wantDir = dir === "<" || dir === ">" ? "row" : "col"
  const hit = focusedHit(ws)
  const level = [...hit.path].reverse().find((p) => p.split.dir === wantDir)
  if (!level) return fail(wantDir === "row" ? tr("no side-by-side split to resize") : tr("no stacked split to resize"), { timeout: 2000 })
  return change(ws, tr("Resize"), () => {
    const { split, index } = level
    const total = split.sizes.reduce((a, b) => a + b, 0)
    const delta = (dir === ">" || dir === "+" ? 1 : -1) * total * 0.05
    const other = index + 1 < split.sizes.length ? index + 1 : index - 1
    const min = total * MIN_SHARE
    const grow = Math.max(min - split.sizes[index], Math.min(delta, split.sizes[other] - min))
    split.sizes[index] += grow
    split.sizes[other] -= grow
  })
})

handle("pane.group", () => {
  const ws = current()
  return change(ws, tr("Link group"), () => {
    const node = focusedHit(ws).node
    node.pinned = false
    node.group = node.group === "A" ? "B" : node.group === "B" ? null : "A"
    status(node.group ? tr("Link group {group}", { group: node.group }) : tr("Not linked"), { timeout: 2000 })
  })
})

handle("pane.pin", () => {
  const ws = current()
  return change(ws, tr("Pin"), () => {
    const node = focusedHit(ws).node
    node.pinned = !node.pinned
    status(node.pinned ? tr("Pinned: this pane keeps its subject") : tr("Unpinned"), { timeout: 2000 })
  })
})

handle("layout.reset", async () => {
  const ws = current()
  const { layout } = await fetch(`/m/${ws.mode}/default`).then((r) => r.json())
  return change(ws, tr("Reset layout"), () => {
    ws.tree = layout
    ws.buffers = []
    ws.max = null
  })
})

handle("layout.save", async ([...words]) => {
  const name = words.join(" ").trim()
  const result = await serverRun("layout.save", [name], { layout: current().tree })
  if (result) status(result.message, { kind: "good" })
  return Boolean(result)
})

handle("layout.load", async ([...words]) => {
  const name = words.join(" ").trim()
  const { layouts } = await fetch("/layouts/").then((r) => r.json())
  const saved = layouts.find((l) => l.name === name)
  if (!saved) return fail(tr("no layout '{name}'", { name }), { kind: "error" })
  const ws = current()
  return change(ws, tr("Load layout {name}", { name }), () => {
    ws.tree = clone(saved.layout)
    ws.max = null
  })
})

export async function layoutNames() {
  const { layouts } = await fetch("/layouts/").then((r) => r.json())
  return layouts.map((l) => l.name)
}

export const bufferIds = () => (current()?.buffers || []).map((b) => b.id)

// ── UI toggles (per browser) ───────────────────────────────────────────────────────────────────────────────────

const TOGGLES = ["no-appbar", "no-keystrips", "is-zen"]

function toggleShell(className) {
  const on = document.getElementById("shell").classList.toggle(className)
  storage(`ui.${className}`, on)
}
handle("ui.appbar", () => toggleShell("no-appbar"))
handle("ui.keystrips", () => toggleShell("no-keystrips"))
handle("ui.zen", () => toggleShell("is-zen"))

export function restoreToggles() {
  for (const className of TOGGLES) {
    if (storage(`ui.${className}`)) document.getElementById("shell").classList.add(className)
  }
}

window.addEventListener("popstate", () => {
  const mode = location.pathname.split("/")[1]
  if (window.SPOS.modes[mode]) switchMode(mode, { push: false })
})
