// Generic behaviour of List views and Sections (spec 05 · E, 03 §5), plus link-group following (spec 03 §4).
// A list is [data-list] with rows [data-row]; its cursor and selection live on the element.

import { addDynamicPrefix } from "./keys.js"
import { handle, run } from "./commands.js"
import { ctx, emit, on, setLayer, status, updateStatus } from "./context.js"

const state = new WeakMap() // list element → {cursor, selected:Set, anchor}

function focusedList() {
  return ctx.pane?.el?.querySelector("[data-list]") || null
}

function listState(list) {
  if (!state.has(list)) state.set(list, { cursor: -1, selected: new Set(), anchor: null })
  return state.get(list)
}

const rowsOf = (list) => [...list.querySelectorAll("[data-row]")]

function paint(list) {
  const st = listState(list)
  rowsOf(list).forEach((row, i) => {
    const selected = st.selected.has(row.dataset.row)
    row.classList.toggle("is-cursor", i === st.cursor)
    row.classList.toggle("is-selected", selected)
    row.setAttribute("aria-selected", String(selected))
    const mark = row.querySelector(".list__mark")
    if (mark) mark.textContent = selected ? "▣" : "▢"
  })
  syncSelection(list)
}

function syncSelection(list) {
  const st = listState(list)
  ctx.selection = { count: st.selected.size, visual: st.anchor !== null }
  const row = rowsOf(list)[st.cursor]
  if (ctx.pane) ctx.pane.subject = row ? `${row.dataset.row} ${row.dataset.title || ""}`.trim() : ""
  updateStatus()
}

function moveTo(list, index) {
  const rows = rowsOf(list)
  if (!rows.length) return false
  const st = listState(list)
  st.cursor = Math.max(0, Math.min(rows.length - 1, index))
  if (st.anchor !== null) {
    const [a, b] = [Math.min(st.anchor, st.cursor), Math.max(st.anchor, st.cursor)]
    st.selected = new Set(st.visualBase)
    rows.slice(a, b + 1).forEach((r) => st.selected.add(r.dataset.row))
  }
  paint(list)
  rows[st.cursor].scrollIntoView({ block: "nearest" })
  const row = rows[st.cursor]
  if (ctx.pane?.group) emit("cursor", { group: ctx.pane.group, from: ctx.pane.id, id: row.dataset.row, title: row.dataset.title, fen: row.dataset.fen })
}

const withList = (fn) => (args) => {
  const list = focusedList()
  if (!list) return false
  return fn(list, listState(list), args)
}

handle("list.down", withList((list, st) => moveTo(list, st.cursor + 1)))
handle("list.up", withList((list, st) => moveTo(list, st.cursor - 1)))
handle("list.first", withList((list) => moveTo(list, 0)))
handle("list.last", withList((list) => moveTo(list, rowsOf(list).length - 1)))

handle("list.select", withList((list, st) => {
  const row = rowsOf(list)[st.cursor]
  if (!row) return moveTo(list, 0)
  const id = row.dataset.row
  st.selected.has(id) ? st.selected.delete(id) : st.selected.add(id)
  paint(list)
}))

handle("list.visual", withList((list, st) => {
  if (st.anchor !== null) {
    st.anchor = null
    setLayer("normal")
    paint(list)
    return
  }
  if (st.cursor < 0) st.cursor = 0
  st.anchor = st.cursor
  st.visualBase = new Set(st.selected)
  setLayer("visual")
  moveTo(list, st.cursor)
}))

handle("list.selectall", withList((list, st) => {
  st.selected = new Set(rowsOf(list).map((r) => r.dataset.row))
  paint(list)
}))

handle("list.open", withList((list, st) => {
  const row = rowsOf(list)[Math.max(0, st.cursor)] // no cursor yet: the first row
  if (!row) return false
  row.classList.remove("is-flash-row")
  void row.offsetWidth
  row.classList.add("is-flash-row")
  if (row.dataset.position) {
    // Positions open in Analyse; n / N there step through the rest of the list.
    const rows = rowsOf(list).filter((r) => r.dataset.position)
    const ids = rows.map((r) => r.dataset.position)
    return window.SPOS.analysis.open(row.dataset.position, { node: Number(row.dataset.node) || null, list: { ids, index: rows.indexOf(row) } })
  }
  status(`Open ${row.dataset.row} ${row.dataset.title}: a demo row, nothing to open`, { timeout: 3000 })
}))

/** Esc steps: leave visual, then clear the selection. Returns true if it did something. */
export function escapeSelection() {
  const list = focusedList()
  if (!list) return false
  const st = listState(list)
  if (st.anchor !== null) {
    st.anchor = null
    setLayer("normal")
    paint(list)
    return true
  }
  if (st.selected.size) {
    st.selected.clear()
    paint(list)
    return true
  }
  return false
}

// Mouse: click moves the cursor, double click opens.
document.addEventListener("click", (e) => {
  const row = e.target.closest("[data-list] [data-row]")
  if (!row || e.target.closest("[data-cmd]")) return
  const list = row.closest("[data-list]")
  moveTo(list, rowsOf(list).indexOf(row))
})
document.addEventListener("dblclick", (e) => {
  if (e.target.closest("[data-list] [data-row]")) run("list.open", [], { source: "mouse" })
})

on("focus", () => {
  const list = focusedList()
  if (list) syncSelection(list)
  else {
    ctx.selection = { count: 0 }
    updateStatus()
  }
})

// ── Link groups: previews follow the cursor of their group ─────────────────────────────────────────────────────

on("cursor", ({ group, from, id, title, fen }) => {
  for (const pane of document.querySelectorAll(".workspace:not([hidden]) [data-pane]")) {
    if (pane.dataset.pane === from) continue
    const link = pane.querySelector("[data-pane-link]")
    if (!link || link.hidden || link.dataset.group !== group) continue
    const preview = pane.querySelector("[data-preview]")
    if (!preview) continue
    preview.querySelector("[data-preview-title]").textContent = title
    preview.querySelector("[data-preview-id]").textContent = id
    const board = preview.querySelector("[data-preview-board]")
    if (board) {
      board.hidden = !fen
      if (fen) {
        board.src = `/svg/board/?${new URLSearchParams({ fen, size: 256 })}`
        board.alt = `Position ${fen}`
      }
    }
  }
})

// ── Sections: z / Z, click on a header, g + letter ────────────────────────────────────────────────────────────

const sectionCursor = new WeakMap() // pane element → section element

function currentSection() {
  const pane = ctx.pane?.el
  if (!pane) return null
  const remembered = sectionCursor.get(pane)
  if (remembered?.isConnected) return remembered
  const body = pane.querySelector(".pane__body")
  const top = body?.getBoundingClientRect().top ?? 0
  return [...pane.querySelectorAll("[data-section]")].find((s) => s.getBoundingClientRect().bottom > top) || null
}

function setSectionCursor(section) {
  const pane = section.closest("[data-pane]")
  pane.querySelectorAll("[data-section].is-cursor").forEach((s) => s.classList.remove("is-cursor"))
  section.classList.add("is-cursor")
  sectionCursor.set(pane, section)
}

export function setCollapsed(section, collapsed) {
  if (section.hasAttribute("data-pinned")) return
  section.classList.toggle("is-collapsed", collapsed)
  section.querySelector(".section__header")?.setAttribute("aria-expanded", String(!collapsed))
}

handle("section.toggle", () => {
  const section = currentSection()
  if (!section) return false
  setSectionCursor(section)
  setCollapsed(section, !section.classList.contains("is-collapsed"))
})

function moveSection(step) {
  const sections = [...(ctx.pane?.el?.querySelectorAll("[data-section]") || [])]
  if (!sections.length) return false
  const current = currentSection()
  const index = current ? sections.indexOf(current) : -1
  const next = sections[Math.max(0, Math.min(sections.length - 1, index + step))]
  setSectionCursor(next)
  next.scrollIntoView({ block: "start" })
}
handle("section.next", () => moveSection(1))
handle("section.prev", () => moveSection(-1))

handle("section.all", () => {
  const sections = [...(ctx.pane?.el?.querySelectorAll("[data-section]") || [])]
  const collapse = sections.some((s) => !s.classList.contains("is-collapsed"))
  sections.forEach((s) => setCollapsed(s, collapse))
})

document.addEventListener("click", (e) => {
  const header = e.target.closest("[data-section-toggle]")
  if (!header || e.target.closest("[data-cmd]")) return
  const section = header.closest("[data-section]")
  setSectionCursor(section)
  run("section.toggle", [], { source: "mouse" })
})

addDynamicPrefix((seq) => {
  if (seq.join(" ") !== "g" || !ctx.pane?.el) return []
  return [...ctx.pane.el.querySelectorAll("[data-section-key]")].map((section) => ({
    key: section.dataset.sectionKey,
    label: `Section: ${section.querySelector(".section__title")?.textContent || ""}`,
    action: () => {
      setCollapsed(section, false)
      setSectionCursor(section)
      section.scrollIntoView({ block: "start" })
    },
  }))
})

// ── Style guide helpers ────────────────────────────────────────────────────────────────────────────────────────

handle("demo.flash", () => status("Every button of this command flashed.", { kind: "good", timeout: 2000 }))

handle("search.open", () => {
  const field = ctx.pane?.el?.querySelector("[data-search]")
  if (!field) return false
  field.focus()
})

// SegmentedControl and Toggle without a command (style guide only): local state.
document.addEventListener("click", (e) => {
  const option = e.target.closest("[data-segmented] [role=radio]")
  if (option && !option.dataset.cmd) {
    option.parentElement.querySelectorAll("[role=radio]").forEach((o) => o.setAttribute("aria-checked", String(o === option)))
  }
  const toggle = e.target.closest("[data-toggle]")
  if (toggle && !toggle.dataset.cmd) toggle.setAttribute("aria-pressed", String(toggle.getAttribute("aria-pressed") !== "true"))
})
