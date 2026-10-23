// Lines: what a board (or a whole link group) is looking at: a start FEN, the moves played from it, the ply shown,
// and the drawings per ply. Panes in one link group share a line (spec 03 §4). In Analyse the analysis tree owns the
// line (a delegate); elsewhere a new move after a step back replaces the rest of the line.
//
// Lines are kept per mode and saved with the mode's UI state, so a reload shows the same position.

import { Chess } from "../../vendor/chess.js"
import { pushUndo } from "./commands.js"
import { ctx, emit, on, status } from "./context.js"

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
const lines = new Map() // "mode:key" → line
const saveTimers = new Map()
const delegates = new Map() // "mode:key" → an analysis tree that owns this line (core/analysis.js)

/**
 * Hand a line over to an owner (the analysis tree): moves, stepping, drawings and loading then go to it, and it
 * sets the line (the path to its cursor) with setLine. null gives the line back.
 */
export function setDelegate(key, delegate) {
  if (delegate) delegates.set(key, delegate)
  else delegates.delete(key)
}
export const delegateOf = (key) => delegates.get(key) || null

const clone = (line) => JSON.parse(JSON.stringify(line))

function emptyLine(start = START_FEN) {
  return { start, moves: [], ply: 0, shapes: {}, squares: {}, title: "" }
}

/** The line key of a pane: its link group, or the pane itself when unlinked or pinned. */
export function keyOf(mode, node) {
  return node.group && !node.pinned ? `${mode}:${node.group}` : `${mode}:${node.id}`
}

export function getLine(key) {
  if (!lines.has(key)) lines.set(key, emptyLine())
  return lines.get(key)
}

export const fenAt = (line, ply = line.ply) => (ply ? line.moves[ply - 1].fen : line.start)

/** Replace a line (loading a position, leaving setup, undo). `undo`: label of the undo step, or null. */
export function setLine(key, next, { undo = null, persist = true } = {}) {
  const before = clone(getLine(key))
  lines.set(key, next)
  emit("line", { key })
  if (persist) save(key)
  if (undo) {
    const after = clone(next)
    pushUndo({ label: undo, undo: () => setLine(key, clone(before), { persist }), redo: () => setLine(key, clone(after), { persist }) })
  }
}

/** Play a move (chess.js verbose move) at the line's current ply. */
export function play(key, move) {
  if (delegates.has(key)) return delegates.get(key).play(move)
  const line = clone(getLine(key))
  const replaced = line.moves.length - line.ply
  line.moves = line.moves.slice(0, line.ply)
  line.moves.push({ uci: move.from + move.to + (move.promotion || ""), san: move.san, fen: move.after })
  line.ply = line.moves.length
  setLine(key, line, { undo: `Move ${move.san}` })
  if (replaced > 0) status(`${move.san} replaced ${replaced} move${replaced > 1 ? "s" : ""} (Analyse keeps variations)`, { timeout: 4000 })
}

export function goTo(key, ply) {
  if (delegates.has(key)) return delegates.get(key).goTo(ply)
  const line = getLine(key)
  const target = Math.max(0, Math.min(line.moves.length, ply))
  if (target === line.ply) return false
  line.ply = target
  emit("line", { key, step: true })
  save(key)
}

export function setShapes(key, shapes) {
  if (delegates.has(key)) return delegates.get(key).setShapes(shapes)
  const line = getLine(key)
  if (shapes.length) line.shapes[line.ply] = shapes
  else delete line.shapes[line.ply]
  emit("line", { key, shapes: true })
  save(key)
}

/** Square highlights (the square tool) at the current ply: {e4: "green", …}. */
export function setSquares(key, squares) {
  if (delegates.has(key)) return delegates.get(key).setSquares(squares)
  const line = getLine(key)
  line.squares ||= {}
  if (Object.keys(squares).length) line.squares[line.ply] = squares
  else delete line.squares[line.ply]
  emit("line", { key, shapes: true })
  save(key)
}

/** Load a position or a game (from paste detection or the library cursor). */
export function load(key, { start = START_FEN, moves = [], title = "" }, { undo = "Load position", persist = true } = {}) {
  if (delegates.has(key) && persist !== "local") return delegates.get(key).load({ start, moves, title })
  const line = emptyLine(start)
  line.title = title
  try {
    const chess = new Chess(start)
    for (const uci of moves) {
      const move = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
      line.moves.push({ uci, san: move.san, fen: move.after })
    }
  } catch (err) {
    status(`could not replay the moves: ${err.message}`, { kind: "error" })
  }
  line.ply = line.moves.length
  setLine(key, line, { undo, persist })
}

/** PGN of a line, with FEN headers when it doesn't start from the initial position. */
export function pgnOf(line) {
  const headers = []
  if (line.start !== START_FEN) headers.push(`[SetUp "1"]`, `[FEN "${line.start}"]`)
  const [, side, , , , full] = line.start.split(" ")
  let number = Number(full) || 1
  let white = side !== "b"
  const parts = []
  line.moves.forEach((m, i) => {
    if (white) parts.push(`${number}.`)
    else if (i === 0) parts.push(`${number}...`)
    parts.push(m.san)
    if (!white) number++
    white = !white
  })
  parts.push("*")
  return (headers.length ? headers.join("\n") + "\n\n" : "") + parts.join(" ")
}

// ── Persistence with the mode's UI state ───────────────────────────────────────────────────────────────────────

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function save(key) {
  const mode = key.split(":")[0]
  clearTimeout(saveTimers.get(mode))
  saveTimers.set(mode, setTimeout(() => flush(mode), 600))
}

function flush(mode) {
  clearTimeout(saveTimers.get(mode))
  saveTimers.delete(mode)
  const payload = {}
  for (const [k, line] of lines) {
    if (!k.startsWith(`${mode}:`) || delegates.has(k)) continue // an analysis saves itself
    payload[k.slice(mode.length + 1)] = {
      start: line.start, moves: line.moves.map((m) => m.uci), ply: line.ply, shapes: line.shapes, squares: line.squares, title: line.title,
    }
  }
  fetch(`/state/${mode}/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ subject: { lines: payload } }),
    keepalive: true, // also when the page is going away
  }).catch(() => {})
}

// A reload right after a move still keeps it.
for (const type of ["beforeunload", "pagehide"]) addEventListener(type, () => { for (const mode of [...saveTimers.keys()]) flush(mode) })

/** Restore a mode's lines from the subject the server rendered into its workspace. */
on("workspace", ({ mode, el }) => {
  const script = el.querySelector(`:scope > script#subject-${mode}`)
  const subject = script ? JSON.parse(script.textContent || "{}") : {}
  for (const [k, saved] of Object.entries(subject.lines || {})) {
    const key = `${mode}:${k}`
    if (lines.has(key)) continue
    load(key, { start: saved.start || START_FEN, moves: saved.moves || [], title: saved.title || "" }, { undo: null, persist: false })
    const line = getLine(key)
    line.ply = Math.min(saved.ply ?? line.moves.length, line.moves.length)
    line.shapes = saved.shapes || {}
    line.squares = saved.squares || {}
  }
})

// Browsing a list moves the boards of its link group (spec 03 §4: Library browsing).
on("cursor", ({ group, fen, title }) => {
  if (!fen) return
  load(`${ctx.mode}:${group}`, { start: fen, title }, { undo: null })
})
