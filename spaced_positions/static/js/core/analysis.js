// The analysis in the browser (spec 04 · Analyse, 09 §6): the tree of the position a link group analyses, its
// cursor, and the panes that show it. Stepping needs no request; every change goes to the server, which answers
// with the whole tree, the move tree HTML and a journal entry for undo (spec 09 §5).

import { handle, pushUndo } from "./commands.js"
import { ctx, emit, on, setLayer, status } from "./context.js"
import { offer, suggest } from "./confirm.js"
import { focusPane, nodeOf, switchMode } from "./layout.js"
import * as lines from "./lines.js"
import { openMenu } from "./menu.js"
import { openCmdline } from "./cmdline.js"
import { setCollapsed } from "./lists.js"
import { tr, trn } from "./i18n.js"

const trees = new Map() // "analyse:A" → tree
const NAG_SYMBOLS = { 1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!", 7: "□", 10: "=", 13: "∞", 14: "⩲", 15: "⩱", 16: "±", 17: "∓", 18: "+−", 19: "−+" }
const LINE_COLOURS = [[tr("Blue"), "#2f80ed"], [tr("Violet"), "#9b51e0"], [tr("Orange"), "#f2994a"], [tr("Green"), "#27ae60"], [tr("Red"), "#eb5757"], [tr("Grey"), "#828282"]]

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) })
    .then(async (r) => ({ status: r.status, data: await r.json().catch(() => ({ ok: false, message: `error ${r.status}` })) }))
    .catch(() => ({ status: 0, data: { ok: false, message: tr("the app is not reachable") } }))

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

/** The analysis the focused pane looks at: its link group in this mode (A by default). Any mode can hold one: a
 *  board and a move tree beside the Library's list (`o`), beside Train's board (`a`), or wherever the user put them. */
export function currentKey() {
  const pane = ctx.pane?.el
  const node = pane ? nodeOf(pane) : null
  return `${ctx.mode}:${node?.group && !node.pinned ? node.group : "A"}`
}

/** Whether this mode has panes for an analysis in the focused link group (`:analyse` opens it there). */
function analysisPanesHere() {
  const [mode, group] = currentKey().split(":")
  return panesFor(`${mode}:${group}`, "moves").length > 0
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

function apply(key, data, { cursor = null, changed = false } = {}) {
  const old = trees.get(key)
  const t = build(data.tree)
  t.cursor = cursor ?? (old?.position.id === t.position.id ? survivor(old, t) : t.root)
  t.list = old?.list || null
  trees.set(key, t)
  t.html = data.html
  renderMoves(key)
  emit("analysis:tree", { key })
  if (changed) emit("analysis:changed", { key, position: t.position.id }) // the Library's work lists follow
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
  for (const [key, t] of trees) if (t.position.id === data.tree.position.id) apply(key, { tree: data.tree, html: data.html }, { changed: true })
}

/** Open a position for analysis in a link group: in Analyse (switching to it), or with `stay` where it is (a mode
 *  that shows an analysis of that group, e.g. Analyse's own Library pane or a Moves pane beside the Library). */
export async function openPosition(pid, { node = null, key = "analyse:A", list = null, show = true, stay = false } = {}) {
  if (show && !stay && ctx.mode !== "analyse") await switchMode("analyse")
  endPreview(key)
  const { data } = await fetch(`/analysis/${pid}/`).then(async (r) => ({ data: await r.json() })).catch(() => ({ data: { ok: false } }))
  if (!data.ok) return status(tr("Could not open that position"), { kind: "error" }) || false
  attach(key)
  apply(key, data, { cursor: node })
  const t = trees.get(key)
  if (list) t.list = list
  const total = t.list ? t.list.count ?? t.list.ids.length : 0
  if (show) status(`${t.position.title || tr("Position")}${total ? ` · ${t.list.index + 1} / ${total}` : ""}`, { timeout: 3000 })
}

// ── Preview: the row under a list's cursor, shown in the move trees of its group without opening it ─────────

const previewing = new Map() // key → the position id shown as a preview
let previewTicket = 0

export async function previewPosition(key, pid, { title = "" } = {}) {
  const ticket = ++previewTicket
  previewing.set(key, pid)
  const data = await fetch(`/analysis/${pid}/`).then((r) => r.json()).catch(() => null)
  if (!data?.ok || ticket !== previewTicket || previewing.get(key) !== pid) return
  for (const el of panesFor(key, "moves")) {
    if (!el.dataset.previewing) originals.set(el, el.innerHTML)
    el.dataset.previewing = "1"
    const banner = document.createElement("div")
    banner.className = "moves__preview"
    banner.textContent = tr("Preview: {title} · ↵ or a opens it · leave the list to go back", { title: data.tree.position.title || title || tr("Position") })
    el.innerHTML = data.html
    el.prepend(banner)
  }
}

const originals = new WeakMap() // a Moves pane → what it showed before the preview (an empty pane's hint)

function endPreview(key) {
  if (!previewing.delete(key)) return
  previewTicket++
  for (const el of panesFor(key, "moves")) {
    if (!el.dataset.previewing) continue
    delete el.dataset.previewing
    if (trees.has(key)) {
      el.innerHTML = trees.get(key).html
      paintFolds(key, el)
    } else {
      el.innerHTML = originals.get(el) ?? ""
    }
  }
  if (trees.has(key)) paintCursor(key)
}

on("preview:end", ({ key }) => endPreview(key))
// The preview lasts while the list has the focus (as the boards' preview in lines.js).
on("focus", ({ pane } = {}) => {
  for (const key of [...previewing.keys()]) {
    const [mode, group] = key.split(":")
    if (mode !== ctx.mode || !pane?.el?.querySelector("[data-list]") || pane.group !== group) endPreview(key)
  }
})
on("mode", () => { for (const key of [...previewing.keys()]) endPreview(key) })

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
  apply(key, data, { cursor: data.node, changed: true })
}

/** The main line from the start (the eval graph, `:evaluate`). */
export function mainlineOf(t) {
  const out = [t.nodes.get(t.root)]
  let id = t.root
  while (kidsOf(t, id)[0]) {
    id = kidsOf(t, id)[0].id
    out.push(t.nodes.get(id))
  }
  return out
}

export { moveTo, kidsOf, path }

/** Store engine evaluations ({node id: {cp, mate, depth}}) and show them. */
export async function saveEvals(key, evals) {
  const t = trees.get(key)
  const { data } = await post(`/analysis/${t.position.id}/evals/`, { evals })
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  apply(key, data, { changed: true })
  status(data.message, { kind: "good", timeout: 3000 })
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
  apply(key, data, { cursor: cursor ?? data.node ?? t.cursor, changed: true })
  if (data.message) status(data.message, { kind: "good", timeout: 4000 })
  return { ...data, code }
}

/** A position or game pasted onto the analysis' board: its moves are added (as a variation where they differ),
 *  starting where the analysis has its position; replacing the analysis is offered, never the default. */
async function loadIntoAnalysis(key, game) {
  const t = trees.get(key)
  const title = t.position.title || tr("this position")
  const same = (a, b) => a.split(" ").slice(0, 4).join(" ") === b.split(" ").slice(0, 4).join(" ")
  const nodes = [t.nodes.get(t.cursor), t.nodes.get(t.root), ...t.nodes.values()]
  const from = nodes.find((n) => n && same(n.fen, game.start))
  const replace = { key: "r", label: tr("replace the moves of “{title}” instead", { title }), run: () => change(key, "replace", { start: game.start, moves: game.moves }) }
  const asNew = { key: "n", label: tr("analyse it as a new position"), run: () => analyseNew({ start: game.start, moves: game.moves, title: game.title, origin: "paste" }) }
  if (!from) {
    // another position: nothing to add it to
    return suggest(tr("The pasted position isn't in this analysis"), [asNew, replace])
  }
  if (!game.moves.length) {
    moveTo(key, from.id)
    return suggest(tr("Already in the analysis: the cursor went there"), [asNew])
  }
  const result = await change(key, "line", { parent: from.id, ucis: game.moves, origin: "paste" })
  if (!result?.ok) return
  suggest(trn("Added {n} pasted move to the analysis (u undoes)", "Added {n} pasted moves to the analysis (u undoes)", game.moves.length), [replace, asNew])
}

/** Correcting the position in the board editor (spec 06 §4): keep the analysis if its moves stay legal. */
export async function correctPosition(key, fen) {
  const t = trees.get(key)
  const result = await change(key, "position", { fen })
  if (result && !result.ok && result.conflict) {
    offer(`${result.message}. ${tr("Drop them? y / n")}`, {
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
    paintFolds(key, el)
  }
}

// ── Folded variations (05 · MoveTree): `z` folds the variation at the cursor, `Z` all of them ─────────────────

const folds = new Map() // position id → the start node ids of its folded variations

const foldsOf = (t) => {
  if (!folds.has(t.position.id)) folds.set(t.position.id, new Set())
  return folds.get(t.position.id)
}

function paintFolds(key, el) {
  const folded = foldsOf(trees.get(key))
  for (const v of el.querySelectorAll("[data-variation]")) {
    const on = folded.has(Number(v.dataset.variation))
    v.classList.toggle("is-folded", on)
    v.querySelector(":scope > [data-fold]")?.setAttribute("aria-expanded", String(!on))
  }
}

function setFolds(key, change) {
  const t = trees.get(key)
  change(foldsOf(t))
  for (const el of panesFor(key, "moves")) paintFolds(key, el)
}

/** The cursor may not hide in a folded variation: the variations around it open (its first move stays visible). */
function unfoldAround(key, el) {
  const cursor = el.querySelector(".mt-move.is-cursor")
  const folded = foldsOf(trees.get(key))
  for (let v = cursor?.closest(".mt-variation"); v; v = v.parentElement.closest(".mt-variation")) {
    const first = v.querySelector(":scope > .mt-label + .mt-move")
    if (folded.has(Number(v.dataset.variation)) && first !== cursor) folded.delete(Number(v.dataset.variation))
  }
  paintFolds(key, el)
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
    unfoldAround(key, el)
    el.querySelector(".is-cursor")?.scrollIntoView({ block: "nearest" })
    const subject = el.closest("[data-pane]")?.querySelector("[data-pane-subject]")
    if (subject) subject.textContent = t.position.title || ""
  }
}

const inspectorTimers = new Map()
// The newest request per analysis and pane kind: an older answer that arrives later is dropped (two quick changes
// at the same move would otherwise show the first one's result).
const requests = new Map()
const ticket = (key, kind) => {
  const n = (requests.get(`${key}:${kind}`) || 0) + 1
  requests.set(`${key}:${kind}`, n)
  return () => requests.get(`${key}:${kind}`) === n
}
function scheduleInspector(key) {
  clearTimeout(inspectorTimers.get(key))
  inspectorTimers.set(key, setTimeout(() => renderInspector(key), 120))
}

async function renderInspector(key) {
  renderPuzzle(key)
  const t = trees.get(key)
  const panes = panesFor(key, "inspector")
  if (!t || !panes.length) return
  const node = t.cursor
  const newest = ticket(key, "inspector")
  const html = await fetch(`/analysis/${t.position.id}/inspector/?node=${node}`).then((r) => r.text()).catch(() => null)
  if (html === null || !newest() || trees.get(key)?.cursor !== node) return
  for (const el of panes) {
    if (el.contains(document.activeElement) && document.activeElement.matches("textarea")) continue // don't replace a comment being written
    el.innerHTML = html
    window.htmx?.process(el)
  }
}

/** The Puzzle pane: the puzzle setup at the cursor, and where the analysis is in its list (n / N). */
async function renderPuzzle(key) {
  const t = trees.get(key)
  const panes = panesFor(key, "puzzle")
  if (!t || !panes.length) return
  const node = t.cursor
  const count = t.list ? t.list.count ?? t.list.ids.length : 0
  const list = count ? `&list=${t.list.index}/${count}` : ""
  const newest = ticket(key, "puzzle")
  const html = await fetch(`/analysis/${t.position.id}/puzzle-pane/?node=${node}${list}`).then((r) => r.text()).catch(() => null)
  if (html === null || !newest() || trees.get(key)?.cursor !== node) return
  for (const el of panes) {
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
    const caret = e.target.closest("[data-fold]")
    if (caret) {
      const id = Number(caret.closest("[data-variation]").dataset.variation)
      return setFolds(keyOfIsland(el), (f) => (f.has(id) ? f.delete(id) : f.add(id)))
    }
    const mv = e.target.closest("[data-node]")
    if (mv) moveTo(keyOfIsland(el), Number(mv.dataset.node))
  })
}

export function mountInspector(el) {
  const key = keyOfIsland(el)
  if (trees.has(key)) renderInspector(key)
}

export function mountPuzzle(el) {
  const key = keyOfIsland(el)
  if (trees.has(key)) renderPuzzle(key)
  el.addEventListener("click", (e) => {
    const target = e.target.closest("[data-node]:not([data-puzzlepane])") // a move of a line, a puzzle's start
    if (target) moveTo(keyOfIsland(el), Number(target.dataset.node))
  })
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
  if (!t) return status(tr("No position open: :analyse, or paste one (⌘V, a)"), { kind: "error" }) || false
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
  return siblings.length > 1 ? moveTo(key, next.id) : status(tr("No other move here"), { timeout: 1500 }) && false
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
handle("analysis.moments", withTree(async (key, t) => {
  status(tr("Looking for the key moments…"), { timeout: 0 })
  const { data } = await post(`/analysis/${t.position.id}/moments/`, {})
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  apply(key, data, { changed: true })
  status(data.message, { kind: "good", timeout: 5000 })
}))

handle("analysis.fold", withTree((key, t) => {
  const el = panesFor(key, "moves")[0]
  const cursor = el?.querySelector(".mt-move.is-cursor")
  if (!cursor) return status(tr("Open the moves pane to fold variations"), { kind: "error" }) || false
  // in a variation: that one; on the main line: the alternatives to the cursor's move, else to the next move
  const blockAfter = (mv) => {
    let next = mv?.nextElementSibling
    while (next && next.matches(".mt-tag, .mt-comment")) next = next.nextElementSibling
    return next?.matches(".mt-variations") ? [...next.children] : []
  }
  const nextMove = (mv) => {
    let next = mv.nextElementSibling
    while (next && !next.matches(".mt-move, .mt-variations")) next = next.nextElementSibling
    return next?.matches(".mt-move") ? next : null
  }
  let targets = cursor.closest(".mt-variation") ? [cursor.closest(".mt-variation")] : blockAfter(cursor)
  if (!targets.length && !cursor.closest(".mt-variation")) targets = blockAfter(nextMove(cursor))
  if (!targets.length) return status(tr("No variation here"), { timeout: 1500 }) || false
  const ids = targets.map((v) => Number(v.dataset.variation))
  const fold = !foldsOf(t).has(ids[0])
  setFolds(key, (f) => ids.forEach((id) => (fold ? f.add(id) : f.delete(id))))
  const first = targets[0].querySelector(":scope > .mt-label + .mt-move")
  if (fold && targets[0].contains(cursor) && first !== cursor) moveTo(key, Number(first.dataset.node))
}))

handle("analysis.foldall", withTree((key, t) => {
  const el = panesFor(key, "moves")[0]
  const all = [...(el?.querySelectorAll("[data-variation]") || [])].map((v) => Number(v.dataset.variation))
  if (!all.length) return status(tr("No variations"), { timeout: 1500 }) || false
  const unfold = foldsOf(t).size > 0
  setFolds(key, (f) => (unfold ? f.clear() : all.forEach((id) => f.add(id))))
  if (!unfold) unfoldAround(key, el)
  status(unfold ? tr("All variations open") : tr("All variations folded · z opens one"), { timeout: 1500 })
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
handle("analysis.subject", withTree(async (key, t, [step]) => {
  let list = t.list
  if (!list) return status(tr("No list here: a in the Library analyses what a search found, n goes through it"), { timeout: 3000 }) || false
  const back = step === "prev"
  let index = list.index + (back ? -1 : 1)
  if (list.q !== undefined) {
    // a live work list: the query runs again, so what was done in the meantime is no longer in it
    const params = new URLSearchParams({ q: list.q, c: list.c || "positions" })
    const data = await fetch(`/lib/subject/?${params}`).then((r) => r.json()).catch(() => null)
    if (!data) return false
    if (!data.ids.length) return status(tr("Nothing left in this list: all done"), { kind: "good", timeout: 4000 }) || false
    const here = data.ids.indexOf(t.position.id)
    // still in the list: its neighbour; done and gone: the one that took its place
    index = here >= 0 ? here + (back ? -1 : 1) : (back ? list.index - 1 : list.index)
    list = { ...list, ids: data.ids, count: data.ids.length }
  }
  if (index < 0 || index >= list.ids.length) {
    return status(back ? tr("This is the first") : tr("This is the last"), { timeout: 1500 }) || false
  }
  await openPosition(list.ids[index], { key, list: { ...list, index }, stay: true })
  emit("analysis:subject", { key, position: list.ids[index] })
}))

const onMove = (fn) => withTree((key, t, args) => (t.cursor === t.root ? status(tr("Go to a move first"), { timeout: 2000 }) || false : fn(key, t, args)))
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
    title: tr("Annotation"),
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
    const color = await openMenu({ title: tr("Line colour"), items: LINE_COLOURS.map(([label, hex], i) => ({ label, key: String(i + 1), keys: [String(i + 1)], value: hex })) })
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
  if (!pane) return status(tr("Open an Inspector pane to write comments: ␣ w v, then i"), { kind: "error" }) || false
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
/** Focus the Puzzle pane of the current analysis (Train's `E`: edit the puzzle). */
export function focusPuzzle() {
  const pane = panesFor(currentKey(), "puzzle")[0]?.closest("[data-pane]")
  if (!pane) return status(tr("Open a Puzzle pane: ␣ w v, then z"), { kind: "error" }) || false
  focusPane(pane.dataset.pane)
}

/** Focus the Inspector of the current analysis and unfold one of its sections (by key: v c t i). */
export function focusInspector(section) {
  const pane = panesFor(currentKey(), "inspector")[0]?.closest("[data-pane]")
  if (!pane) return status(tr("Open an Inspector pane: ␣ w v, then i"), { kind: "error" }) || false
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
  status(`${data.message} · ${moves ? tr("its own analysis, with the continuation") : tr("its own analysis")}`, { kind: "good", timeout: 4000 })
}))

handle("analysis.open", async ([pid]) => {
  if (!pid) return openCmdline("analyse ")
  if (ctx.mode !== "analyse" && analysisPanesHere()) return openPosition(pid, { key: currentKey(), show: false }) // into these panes
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
    shownIn: (key) => ["moves", "inspector", "puzzle"].some((view) => panesFor(key, view).length > 0),
    preview: previewPosition,
    endPreview,
    current,
    focusInspector,
    focusPuzzle,
    analyseNew,
  },
})
