// The analysis in the browser (spec 04 · Analyse, 09 §6): the tree of the position a link group analyses, its
// cursor, and the panes that show it. Stepping needs no request; every change goes to the server, which answers
// with the whole tree, the move tree HTML and a journal entry for undo (spec 09 §5).

import { handle, pushUndo } from "./commands.js"
import { ctx, emit, on, setLayer, status } from "./context.js"
import { offer } from "./confirm.js"
import { focusPane, nodeOf, switchMode } from "./layout.js"
import * as lines from "./lines.js"
import { openMenu } from "./menu.js"
import { openCmdline } from "./cmdline.js"
import { setCollapsed } from "./lists.js"

const trees = new Map() // "analyse:A" → tree
const NAG_SYMBOLS = { 1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!", 7: "□", 10: "=", 13: "∞", 14: "⩲", 15: "⩱", 16: "±", 17: "∓", 18: "+−", 19: "−+" }
const LINE_COLOURS = [["Blue", "#2f80ed"], ["Violet", "#9b51e0"], ["Orange", "#f2994a"], ["Green", "#27ae60"], ["Red", "#eb5757"], ["Grey", "#828282"]]

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) })
    .then(async (r) => ({ status: r.status, data: await r.json().catch(() => ({ ok: false, message: `error ${r.status}` })) }))
    .catch(() => ({ status: 0, data: { ok: false, message: "the app is not reachable" } }))

// ── The tree of a key ─────────────────────────────────────────────────────────────────────────────────────────

function build(data) {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]))
  const kids = new Map()
  for (const n of data.nodes) {
    if (n.parent === null) continue
    if (!kids.has(n.parent)) kids.set(n.parent, [])
    kids.get(n.parent).push(n)
  }
  for (const list of kids.values()) list.sort((a, b) => a.order - b.order || a.id - b.id)
  return { nodes, kids, root: data.root, position: data.position, puzzles: data.puzzles }
}

export function treeOf(key) {
  return trees.get(key) || null
}

/** The analysis the focused pane looks at (Analyse mode: its link group, A by default). */
export function currentKey() {
  const pane = ctx.pane?.el
  const node = pane ? nodeOf(pane) : null
  return `analyse:${node?.group && !node.pinned ? node.group : "A"}`
}
export const current = () => treeOf(currentKey())

const kidsOf = (t, id) => t.kids.get(id) || []

function path(t, id) {
  const out = []
  for (let n = t.nodes.get(id); n; n = t.nodes.get(n.parent)) out.push(n)
  return out.reverse()
}

/** Set the board's line to the path from the root to the cursor (with the drawings of each move). */
function showCursor(key) {
  const t = trees.get(key)
  const nodes = path(t, t.cursor)
  const line = {
    start: nodes[0].fen,
    moves: nodes.slice(1).map((n) => ({ uci: n.uci, san: n.san, fen: n.fen })),
    ply: nodes.length - 1,
    shapes: {},
    squares: {},
    title: t.position.title,
  }
  nodes.forEach((n, i) => {
    if (n.shapes?.length) line.shapes[i] = n.shapes
    if (n.squares && Object.keys(n.squares).length) line.squares[i] = n.squares
  })
  lines.setLine(key, line, { persist: false })
  paintCursor(key)
  scheduleInspector(key)
  saveSubject()
  emit("analysis:cursor", { key, node: t.nodes.get(t.cursor) })
}

function moveTo(key, id) {
  const t = trees.get(key)
  if (!t || !t.nodes.has(id) || t.cursor === id) return false
  t.cursor = id
  showCursor(key)
}

function apply(key, data, { cursor = null } = {}) {
  const old = trees.get(key)
  const t = build(data.tree)
  t.cursor = cursor ?? (old?.position.id === t.position.id ? survivor(old, t) : t.root)
  t.list = old?.list || null
  trees.set(key, t)
  t.html = data.html
  renderMoves(key)
  if (data.journal) {
    const entry = data.journal
    pushUndo({ label: entry.label, undo: () => journal(entry.id, "undo"), redo: () => journal(entry.id, "redo") })
  }
  showCursor(key)
}

/** The old cursor, or its nearest ancestor that is still in the tree (after an undo removed moves). */
function survivor(old, t) {
  for (let n = old.nodes.get(old.cursor); n; n = old.nodes.get(n.parent)) if (t.nodes.has(n.id)) return n.id
  return t.root
}

async function journal(id, action) {
  const { data } = await post(`/journal/${id}/${action}/`, {})
  if (!data.ok) return status(data.message, { kind: "error" })
  for (const [key, t] of trees) if (t.position.id === data.tree.position.id) apply(key, { tree: data.tree, html: data.html })
}

/** Open a position for analysis in a link group (switches to Analyse). */
export async function openPosition(pid, { node = null, key = "analyse:A", list = null, show = true } = {}) {
  if (show && ctx.mode !== "analyse") await switchMode("analyse")
  const { data } = await fetch(`/analysis/${pid}/`).then(async (r) => ({ data: await r.json() })).catch(() => ({ data: { ok: false } }))
  if (!data.ok) return status("Could not open that position", { kind: "error" }) || false
  attach(key)
  apply(key, data, { cursor: node })
  const t = trees.get(key)
  if (list) t.list = list
  if (show) status(`${t.position.title || "Position"}${t.list ? ` · ${t.list.index + 1} / ${t.list.ids.length}` : ""}`, { timeout: 3000 })
}

// ── The board's line goes to the tree ─────────────────────────────────────────────────────────────────────────

function attach(key) {
  lines.setDelegate(key, {
    play: (move) => playMove(key, move),
    goTo: (ply) => {
      const t = trees.get(key)
      const nodes = path(t, t.cursor)
      if (ply < nodes.length - 1) return moveTo(key, nodes[Math.max(0, ply)].id)
      let id = t.cursor
      for (let i = nodes.length - 1; i < ply; i++) {
        const next = kidsOf(t, id)[0]
        if (!next) break
        id = next.id
      }
      return moveTo(key, id)
    },
    setShapes: (shapes) => saveDrawing(key, { shapes }),
    setSquares: (squares) => saveDrawing(key, { squares }),
    load: (game) => loadIntoAnalysis(key, game),
    setStart: (fen) => correctPosition(key, fen),
  })
}

async function playMove(key, move) {
  const t = trees.get(key)
  const existing = kidsOf(t, t.cursor).find((n) => n.uci === move.from + move.to + (move.promotion || ""))
  if (existing) return moveTo(key, existing.id)
  // Optimistic: the board shows the move at once; the tree follows when the server answers.
  const line = lines.getLine(key)
  lines.setLine(key, { ...line, moves: [...line.moves.slice(0, line.ply), { uci: move.from + move.to + (move.promotion || ""), san: move.san, fen: move.after }], ply: line.ply + 1 }, { persist: false })
  const { data } = await post(`/analysis/${t.position.id}/play/`, { parent: t.cursor, uci: move.from + move.to + (move.promotion || "") })
  if (!data.ok) {
    status(data.message, { kind: "error" })
    return showCursor(key)
  }
  apply(key, data, { cursor: data.node })
}

/** Add a line of moves (from the engine) after the cursor; moves that exist are reused. */
export function addLine(key, ucis) {
  const t = trees.get(key)
  return change(key, "line", { parent: t.cursor, ucis })
}

const drawingTimers = new Map()
function saveDrawing(key, fields) {
  const t = trees.get(key)
  const node = t.nodes.get(t.cursor)
  Object.assign(node, fields)
  showCursor(key)
  clearTimeout(drawingTimers.get(key))
  drawingTimers.set(key, setTimeout(() => change(key, "edit", { node: node.id, shapes: node.shapes, squares: node.squares }), 400))
}

async function change(key, action, body, { cursor } = {}) {
  const t = trees.get(key)
  if (!t) return false
  const { status: code, data } = await post(`/analysis/${t.position.id}/${action}/`, body)
  if (!data.ok) {
    status(data.message, { kind: "error" })
    return data
  }
  apply(key, data, { cursor: cursor ?? data.node ?? t.cursor })
  if (data.message) status(data.message, { kind: "good", timeout: 4000 })
  return { ...data, code }
}

function loadIntoAnalysis(key, game) {
  const t = trees.get(key)
  offer(`Replace the moves of “${t.position.title || "this position"}” with the pasted ${game.moves.length ? "game" : "position"}? y / n`, {
    y: () => change(key, "replace", { start: game.start, moves: game.moves }),
  })
}

/** Correcting the position in the board editor (spec 06 §4): keep the analysis if its moves stay legal. */
export async function correctPosition(key, fen) {
  const t = trees.get(key)
  const result = await change(key, "position", { fen })
  if (result && !result.ok && result.message?.includes("moves would go")) {
    offer(`The corrected position makes moves of the analysis illegal: ${result.message.split("(")[1]?.replace(")", "") || ""}. Drop them? y / n`, {
      y: () => change(key, "position", { fen, force: true }),
    })
  }
  return t
}

// ── Panes: moves and inspector ────────────────────────────────────────────────────────────────────────────────

function panesFor(key, island) {
  const [mode, group] = key.split(":")
  return [...document.querySelectorAll(`#ws-${mode} [data-island='${island}']`)].filter((el) => {
    const node = nodeOf(el.closest("[data-pane]"))
    return (node?.group && !node.pinned ? node.group : node?.id) === group
  })
}

function renderMoves(key) {
  const t = trees.get(key)
  for (const el of panesFor(key, "moves")) {
    el.innerHTML = t.html
  }
}

function paintCursor(key) {
  const t = trees.get(key)
  const onPath = new Set(path(t, t.cursor).map((n) => n.id))
  for (const el of panesFor(key, "moves")) {
    for (const mv of el.querySelectorAll("[data-node]")) {
      const id = Number(mv.dataset.node)
      mv.classList.toggle("is-cursor", id === t.cursor)
      mv.classList.toggle("is-path", onPath.has(id) && id !== t.cursor)
    }
    el.querySelector(".is-cursor")?.scrollIntoView({ block: "nearest" })
    const subject = el.closest("[data-pane]")?.querySelector("[data-pane-subject]")
    if (subject) subject.textContent = t.position.title || ""
  }
}

const inspectorTimers = new Map()
function scheduleInspector(key) {
  clearTimeout(inspectorTimers.get(key))
  inspectorTimers.set(key, setTimeout(() => renderInspector(key), 120))
}

async function renderInspector(key) {
  const t = trees.get(key)
  const panes = panesFor(key, "inspector")
  if (!t || !panes.length) return
  const node = t.cursor
  const html = await fetch(`/analysis/${t.position.id}/inspector/?node=${node}`).then((r) => r.text()).catch(() => null)
  if (html === null || trees.get(key)?.cursor !== node) return
  for (const el of panes) {
    if (el.contains(document.activeElement) && document.activeElement.matches("textarea")) continue // don't replace a comment being written
    el.innerHTML = html
    window.htmx?.process(el)
  }
}

export function mountMoves(el) {
  const key = keyOfIsland(el)
  if (trees.has(key)) {
    el.innerHTML = trees.get(key).html
    paintCursor(key)
  }
  el.addEventListener("click", (e) => {
    const mv = e.target.closest("[data-node]")
    if (mv) moveTo(keyOfIsland(el), Number(mv.dataset.node))
  })
}

export function mountInspector(el) {
  const key = keyOfIsland(el)
  if (trees.has(key)) renderInspector(key)
}

function keyOfIsland(el) {
  const pane = el.closest("[data-pane]")
  const node = nodeOf(pane)
  const mode = pane.closest(".workspace").dataset.mode
  return `${mode}:${node?.group && !node.pinned ? node.group : node?.id}`
}

// Comments: saved with ⌘↵ (form.submit) and when the field is left with changes.
async function saveComment(form) {
  const key = keyOfIsland(form)
  const t = trees.get(key)
  const node = Number(form.dataset.node)
  const text = form.querySelector("textarea").value
  if (!t || t.nodes.get(node)?.comment === text) return
  await change(key, "edit", { node, comment: text }, { cursor: t.cursor })
}
export function submitComment(form) {
  return saveComment(form)
}
document.addEventListener("focusout", async (e) => {
  const form = e.target.closest?.("[data-comment-form]")
  if (!form || !e.target.matches("textarea")) return
  await saveComment(form)
  scheduleInspector(keyOfIsland(form)) // the cursor may have moved while the comment was written
})

// Piece symbols in comments: Alt+K Q R B N P (Shift for black).
const FIGURINES = { k: ["♔", "♚"], q: ["♕", "♛"], r: ["♖", "♜"], b: ["♗", "♝"], n: ["♘", "♞"], p: ["♙", "♟"] }
document.addEventListener("keydown", (e) => {
  if (!e.altKey || !e.target.matches?.("[data-comment-form] textarea")) return
  const letter = /^Key([KQRBNP])$/.exec(e.code)?.[1]?.toLowerCase()
  if (!letter) return
  e.preventDefault()
  const area = e.target
  const symbol = FIGURINES[letter][e.shiftKey ? 1 : 0]
  area.setRangeText(symbol, area.selectionStart, area.selectionEnd, "end")
}, true)

// Tags changed (the Library, :tag): the move tree shows move tags, the inspector both kinds.
on("library:changed", async () => {
  for (const [key, t] of trees) {
    const data = await fetch(`/analysis/${t.position.id}/`).then((r) => r.json()).catch(() => null)
    if (data?.ok && trees.get(key)?.position.id === t.position.id) apply(key, data)
  }
})

// ── Subject (what Analyse shows) survives reloads ─────────────────────────────────────────────────────────────

// The server keeps what Analyse shows for the next visit; this tab also keeps it in sessionStorage, written at once,
// so a reload right after a step comes back to the same move even when the save hasn't reached the server yet.
let subjectTimer = null

function subjectNow() {
  const analysis = {}
  for (const [key, t] of trees) if (key.startsWith("analyse:")) analysis[key.slice(8)] = { position: t.position.id, node: t.cursor, list: t.list }
  return analysis
}

function remembered() {
  try {
    return JSON.parse(sessionStorage.getItem("spos.analysis") || "null") || {}
  } catch {
    return {}
  }
}

function saveSubject() {
  try {
    sessionStorage.setItem("spos.analysis", JSON.stringify(subjectNow()))
  } catch {
    // private mode: the server's copy is enough
  }
  clearTimeout(subjectTimer)
  subjectTimer = setTimeout(flushSubject, 600)
}

function flushSubject() {
  clearTimeout(subjectTimer)
  subjectTimer = null
  fetch("/state/analyse/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ subject: { analysis: subjectNow() } }),
    keepalive: true, // also when the page is going away
  }).catch(() => {})
}

for (const type of ["beforeunload", "pagehide"]) addEventListener(type, () => { if (subjectTimer) flushSubject() })

on("workspace", ({ mode, el }) => {
  if (mode !== "analyse") return
  const script = el.querySelector(":scope > script#subject-analyse")
  const subject = script ? JSON.parse(script.textContent || "{}") : {}
  for (const [group, saved] of Object.entries({ ...subject.analysis, ...remembered() })) {
    if (!saved?.position) continue
    if (trees.get(`analyse:${group}`)?.position.id === saved.position) continue
    setTimeout(() => openPosition(saved.position, { node: saved.node, key: `analyse:${group}`, list: saved.list, show: false }), 0)
  }
})

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

const withTree = (fn) => (args) => {
  const key = currentKey()
  const t = trees.get(key)
  if (!t) return status("No position open: :analyse, or paste one (⌘V, a)", { kind: "error" }) || false
  return fn(key, t, args)
}

handle("analysis.back", withTree((key, t) => moveTo(key, t.nodes.get(t.cursor).parent ?? t.cursor)))
handle("analysis.forward", withTree((key, t) => {
  const next = kidsOf(t, t.cursor)[0]
  return next ? moveTo(key, next.id) : false
}))
handle("analysis.start", withTree((key, t) => moveTo(key, t.root)))
handle("analysis.end", withTree((key, t) => {
  let id = t.cursor
  while (kidsOf(t, id)[0]) id = kidsOf(t, id)[0].id
  return moveTo(key, id)
}))
handle("analysis.sibling", withTree((key, t, [step]) => {
  const node = t.nodes.get(t.cursor)
  if (node.parent === null) return false
  const siblings = kidsOf(t, node.parent)
  const i = siblings.findIndex((n) => n.id === node.id)
  const next = siblings[(i + (step === "prev" ? -1 : 1) + siblings.length) % siblings.length]
  return siblings.length > 1 ? moveTo(key, next.id) : status("No other move here", { timeout: 1500 }) && false
}))
handle("analysis.branch", withTree((key, t, [step]) => {
  if (step === "prev") {
    for (let n = t.nodes.get(t.nodes.get(t.cursor).parent); n; n = t.nodes.get(n.parent)) {
      if (kidsOf(t, n.id).length > 1) return moveTo(key, n.id)
    }
    return moveTo(key, t.root)
  }
  let id = t.cursor
  while (kidsOf(t, id).length === 1) id = kidsOf(t, id)[0].id
  return id === t.cursor ? false : moveTo(key, id)
}))
handle("analysis.mainline", withTree((key, t) => {
  // up to the last node that is on the main line (first child all the way from the root)
  const nodes = path(t, t.cursor)
  let last = nodes[0]
  for (const n of nodes.slice(1)) {
    if (kidsOf(t, n.parent)[0]?.id !== n.id) break
    last = n
  }
  return moveTo(key, last.id)
}))
handle("analysis.subject", withTree((key, t, [step]) => {
  const list = t.list
  if (!list) return false
  const index = Math.max(0, Math.min(list.ids.length - 1, list.index + (step === "prev" ? -1 : 1)))
  if (index === list.index) return status(step === "prev" ? "This is the first" : "This is the last", { timeout: 1500 }) && false
  return openPosition(list.ids[index], { key, list: { ...list, index } })
}))

const onMove = (fn) => withTree((key, t, args) => (t.cursor === t.root ? status("Go to a move first", { timeout: 2000 }) || false : fn(key, t, args)))
handle("analysis.nag", onMove((key, t, [n]) => {
  const node = t.nodes.get(t.cursor)
  const value = Number(n)
  const nags = node.nags.includes(value) ? node.nags.filter((x) => x !== value) : [...node.nags.filter((x) => x > 7), value]
  return change(key, "edit", { node: node.id, nags })
}))
handle("analysis.annotate", onMove(async (key, t) => {
  const node = t.nodes.get(t.cursor)
  const keys = "1234567890abcdefgh"
  const value = await openMenu({
    title: "Annotation",
    items: Object.entries(NAG_SYMBOLS).map(([n, symbol], i) => ({ label: `${symbol}${node.nags.includes(Number(n)) ? "  ✓" : ""}`, key: keys[i], keys: [keys[i]], value: n })),
  })
  if (!value) return false
  const v = Number(value)
  const move = v <= 7
  const nags = node.nags.includes(v) ? node.nags.filter((x) => x !== v) : [...node.nags.filter((x) => (move ? x > 7 : x <= 7)), v]
  return change(key, "edit", { node: node.id, nags })
}))
handle("analysis.mark", onMove(async (key, t, [mark]) => {
  const node = t.nodes.get(t.cursor)
  if (mark === "clear") return change(key, "edit", { node: node.id, mark: "", color: "" })
  if (mark === "color") {
    const color = await openMenu({ title: "Line colour", items: LINE_COLOURS.map(([label, hex], i) => ({ label, key: String(i + 1), keys: [String(i + 1)], value: hex })) })
    return color ? change(key, "edit", { node: node.id, color }) : false
  }
  return change(key, "edit", { node: node.id, mark: node.mark === mark ? "" : mark })
}))
handle("analysis.moveup", onMove((key, t) => change(key, "reorder", { node: t.cursor, step: "up" })))
handle("analysis.movedown", onMove((key, t) => change(key, "reorder", { node: t.cursor, step: "down" })))
handle("analysis.promote", onMove((key, t) => change(key, "promote", { node: t.cursor })))
handle("analysis.delete", onMove((key, t) => change(key, "delete", { node: t.cursor })))
handle("analysis.puzzle", withTree((key, t, [action]) => change(key, "puzzle", { node: t.cursor, action })))

async function focusComment(key) {
  const pane = panesFor(key, "inspector")[0]?.closest("[data-pane]")
  if (!pane) return status("Open an Inspector pane to write comments: ␣ w v, then i", { kind: "error" }) || false
  // The comment field must be the one of the move at the cursor, not of the move shown before it. Insert at once:
  // what is typed while the inspector loads must not run commands.
  setLayer("insert")
  if (Number(pane.querySelector("[data-inspector]")?.dataset.node) !== trees.get(key).cursor) {
    clearTimeout(inspectorTimers.get(key))
    await renderInspector(key)
  }
  focusPane(pane.dataset.pane)
  const area = pane.querySelector("[data-comment-form] textarea")
  if (!area) return setLayer("normal") || false
  setCollapsed(area.closest("[data-section]"), false)
  area.focus()
  setLayer("insert")
}
/** Focus the Inspector of the current analysis and unfold one of its sections (by key: v c z i). */
export function focusInspector(section) {
  const pane = panesFor(currentKey(), "inspector")[0]?.closest("[data-pane]")
  if (!pane) return status("Open an Inspector pane: ␣ w v, then i", { kind: "error" }) || false
  focusPane(pane.dataset.pane)
  const open = () => {
    const el = pane.querySelector(`[data-section][data-section-key="${section}"]`)
    if (!el) return false
    setCollapsed(el, false)
    el.scrollIntoView({ block: "start" })
    return true
  }
  if (!open()) setTimeout(open, 400) // the inspector is still loading
}

handle("analysis.comment", withTree((key) => focusComment(key)))
handle("analysis.rootcomment", withTree((key, t) => {
  moveTo(key, t.root)
  return focusComment(key)
}))

handle("analysis.newposition", withTree(async (key, t, [moves]) => {
  const { data } = await post(`/analysis/${t.position.id}/new-position/`, { node: t.cursor, moves: moves === "moves" })
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  await openPosition(data.position, { key })
  status(`${data.message} · its own analysis${moves ? ", with the continuation" : ""}`, { kind: "good", timeout: 4000 })
}))

handle("analysis.open", async ([pid]) => {
  if (!pid) return openCmdline("analyse ")
  return openPosition(pid)
})

/** A new position to analyse from a start and moves (paste → analyse). */
export async function analyseNew({ start, moves = [], title = "", origin = "paste" }) {
  const { data } = await post("/analysis/new/", { start, moves, title, origin })
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  return openPosition(data.position, { node: null })
}

// The undo journal survives reloads: its entries come back onto the undo stack.
export async function loadJournal() {
  const data = await fetch("/journal/").then((r) => r.json()).catch(() => ({ entries: [] }))
  for (const entry of data.entries) {
    pushUndo({ label: entry.label, undo: () => journal(entry.id, "undo"), redo: () => journal(entry.id, "redo") })
  }
}

// `when` lookups (core/context.js) and the entry points of other modules.
Object.assign((window.SPOS ||= {}), {
  analysis: {
    loaded: () => Boolean(current()),
    onMove: () => Boolean(current() && current().cursor !== current().root),
    hasList: () => Boolean(current()?.list),
    open: openPosition,
    openGame: (id, options = {}) => openPosition(id, options), // a game opens like a position (its tree, no puzzles)
    current,
    focusInspector,
    analyseNew,
  },
})
