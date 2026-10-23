// The board island (spec 06): chessground for the board, chess.js for instant legality. Layers: play (moves,
// drawings, square tool), setup (board editor with live validation), entry (typed moves). Boards in a link group
// share a line (core/lines.js); every action is a command, so keys and buttons do the same thing.

import { Chessground } from "../../vendor/chessground.min.js"
import { Chess } from "../../vendor/chess.js"
import { handle, run } from "../core/commands.js"
import { ctx, on, setLayer, status } from "../core/context.js"
import { setOverlayHandler } from "../core/keys.js"
import { nodeOf } from "../core/layout.js"
import * as lines from "../core/lines.js"
import { openMenu } from "../core/menu.js"
import { matchMoves } from "../core/san.js"

const boards = new Set()
const EMPTY = "8/8/8/8/8/8/8/8"
const GLYPHS = {
  white: { pawn: "♙", knight: "♘", bishop: "♗", rook: "♖", queen: "♕", king: "♔" },
  black: { pawn: "♟", knight: "♞", bishop: "♝", rook: "♜", queen: "♛", king: "♚" },
}
const ROLE_OF = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" }

function chessOf(fen) {
  try {
    return new Chess(fen)
  } catch {
    return null // a diagram (illegal position): shown, not playable
  }
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function brushes() {
  const brush = (key, color) => ({ key, color: css(color), opacity: 1, lineWidth: 10 })
  return {
    green: brush("g", "--arrow-green"),
    red: brush("r", "--arrow-red"),
    blue: brush("b", "--arrow-blue"),
    yellow: brush("y", "--arrow-yellow"),
    paleBlue: { key: "pb", color: css("--arrow-engine"), opacity: 0.4, lineWidth: 15 },
    paleGreen: { key: "pg", color: css("--arrow-green"), opacity: 0.4, lineWidth: 15 },
  }
}

function brushFor(e) {
  return ["green", "red", "blue", "yellow"][(e.shiftKey || e.ctrlKey ? 1 : 0) + (e.altKey || e.metaKey ? 2 : 0)]
}

function tokenValue(name, fallback) {
  const themes = window.SPOS.themes.themes
  const theme = themes[ctx.theme] || themes[ctx.prefersDark ? "ink" : "paper"]
  return (window.SPOS.tokens || {})[name] ?? theme?.values?.[name] ?? fallback
}

const colorOf = (turn) => (turn === "w" ? "white" : "black")

class Board {
  constructor(el) {
    this.el = el
    this.pane = el.closest("[data-pane]")
    this.cgEl = el.querySelector(".board__cg")
    this.strip = el.querySelector("[data-board-status]")
    this.palette = el.querySelector("[data-palette]")
    this.orientation = "white"
    this.layer = "play"
    this.squareTool = false
    this.entry = null
    this.setup = null
    this.cg = Chessground(this.cgEl, {
      orientation: this.orientation,
      coordinates: tokenValue("board-coords", "inside") !== "off",
      animation: { enabled: true, duration: Number(tokenValue("board-motion", 150)) * Number(tokenValue("motion", 1)) },
      highlight: { lastMove: true, check: true },
      premovable: { enabled: false },
      draggable: { enabled: true, showGhost: true },
      movable: { free: false, showDests: true, events: { after: (orig, dest) => this.onMove(orig, dest) } },
      drawable: { enabled: true, visible: true, eraseOnClick: true, brushes: brushes(), onChange: (shapes) => this.onShapes(shapes) },
      events: { change: () => this.onSetupChange() },
    })
    this.cgEl.addEventListener("pointerdown", (e) => this.onPointerDown(e), true)
    this.cgEl.addEventListener("contextmenu", (e) => { if (this.layer === "setup" || this.squareTool) e.preventDefault() }, true)
    boards.add(this)
    this.refresh()
    if (el.dataset.startLayer === "setup") this.enterSetup()
  }

  get mode() { return this.pane.closest(".workspace")?.dataset.mode || ctx.mode }
  get node() { return nodeOf(this.pane) || { id: this.pane.dataset.pane } }
  get key() { return lines.keyOf(this.mode, this.node) }
  get line() { return lines.getLine(this.key) }
  get alive() { return this.el.isConnected }
  get focused() { return ctx.pane?.el === this.pane }

  // ── Play ───────────────────────────────────────────────────────────────────────────────────────────────────

  refresh() {
    if (this.layer === "setup") return
    const line = this.line
    const fen = lines.fenAt(line)
    const chess = chessOf(fen)
    const last = line.ply ? line.moves[line.ply - 1].uci : null
    const turn = colorOf(fen.split(" ")[1] || "w")
    const dests = new Map()
    if (chess) for (const m of chess.moves({ verbose: true })) dests.set(m.from, [...(dests.get(m.from) || []), m.to])
    this.cg.set({
      fen,
      orientation: this.orientation,
      turnColor: turn,
      lastMove: last ? [last.slice(0, 2), last.slice(2, 4)] : [],
      check: Boolean(chess?.inCheck()),
      movable: { free: false, color: chess && this.layer !== "readonly" ? turn : undefined, dests },
      draggable: { deleteOnDropOff: false },
      drawable: { enabled: true, shapes: line.shapes[line.ply] || [] },
      highlight: { custom: new Map(Object.entries(line.squares?.[line.ply] || {}).map(([k, b]) => [k, `hl-${b}`])) },
    })
    this.chess = chess
    this.renderStrip()
  }

  async onMove(orig, dest) {
    const chess = chessOf(lines.fenAt(this.line))
    const options = chess?.moves({ verbose: true }).filter((m) => m.from === orig && m.to === dest) || []
    if (!options.length) return this.refresh()
    let promotion
    if (options.length > 1) {
      promotion = await openMenu({
        title: "Promote to",
        anchor: this.cgEl,
        items: [["q", "Queen"], ["r", "Rook"], ["b", "Bishop"], ["n", "Knight"]].map(([key, label]) => ({ label, key, keys: [key], value: key })),
      })
      if (!promotion) return this.refresh()
    }
    lines.play(this.key, chess.move({ from: orig, to: dest, promotion }))
  }

  onShapes(shapes) {
    if (this.layer === "setup") return
    lines.setShapes(this.key, shapes.filter((s) => !s.customSvg))
  }

  onPointerDown(e) {
    // The board can move without resizing (a palette or strip appears, a split moves it): chessground caches its
    // position, so refresh it before chessground or we read it.
    this.cg.state.dom.bounds.clear()
    if (this.layer === "setup") return this.onSetupPointer(e)
    if (this.squareTool && e.button === 2) {
      const key = this.cg.getKeyAtDomPos([e.clientX, e.clientY])
      if (!key) return
      e.preventDefault()
      e.stopPropagation()
      const line = this.line
      const squares = { ...(line.squares?.[line.ply] || {}) }
      const brush = brushFor(e)
      if (squares[key] === brush) delete squares[key]
      else squares[key] = brush
      lines.setSquares(this.key, squares)
    }
  }

  // ── Setup (board editor) ─────────────────────────────────────────────────────────────────────────────────

  enterSetup() {
    const [placement, side = "w", castling = "-", ep = "-"] = lines.fenAt(this.line).split(" ")
    this.leaveEntry()
    this.setup = { role: "pawn", color: "white", tool: "piece", side, castling, ep, diagram: false, check: null }
    this.layer = "setup"
    this.el.dataset.layer = "setup"
    this.cg.set({
      fen: placement,
      lastMove: [],
      check: false,
      movable: { free: true, color: "both", dests: new Map() },
      draggable: { deleteOnDropOff: true },
      drawable: { enabled: false, shapes: [] },
      highlight: { custom: new Map() },
    })
    if (this.palette) this.palette.hidden = false
    if (this.focused) setLayer("setup")
    this.validate()
  }

  fullFen() {
    const s = this.setup
    return `${this.cg.getFen()} ${s.side} ${s.castling || "-"} ${s.ep || "-"} 0 1`
  }

  onSetupPointer(e) {
    const key = this.cg.getKeyAtDomPos([e.clientX, e.clientY])
    if (!key) return
    const s = this.setup
    if (e.button === 2 || s.tool === "eraser") {
      e.preventDefault()
      e.stopPropagation()
      this.cg.setPieces(new Map([[key, undefined]]))
      return this.onSetupChange()
    }
    if (s.tool === "hand" || e.button !== 0) return // chessground drags freely
    e.preventDefault()
    e.stopPropagation()
    const color = e.shiftKey ? (s.color === "white" ? "black" : "white") : s.color
    const current = this.cg.state.pieces.get(key)
    const same = current && current.role === s.role && current.color === color
    this.cg.setPieces(new Map([[key, same ? undefined : { role: s.role, color }]]))
    this.onSetupChange()
  }

  onSetupChange() {
    if (this.layer !== "setup") return
    clearTimeout(this.validateTimer)
    this.validateTimer = setTimeout(() => this.validate(), 120)
    this.renderStrip()
  }

  async validate() {
    const fen = this.fullFen()
    const params = new URLSearchParams({ fen, diagram: this.setup.diagram ? "1" : "" })
    try {
      this.setup.check = await fetch(`/chess/fen/?${params}`).then((r) => r.json())
    } catch {
      this.setup.check = null
    }
    this.renderStrip()
    return this.setup.check
  }

  async leaveSetup() {
    const check = await this.validate()
    if (check && !check.ok && !this.setup.diagram) {
      status(`Not a legal position: ${check.problems.map((p) => p.message).join("; ")}${check.fixed ? " · a fixes it" : ""} · D: keep it as a diagram`, { kind: "error", timeout: 8000 })
      return false
    }
    const fen = this.fullFen()
    this.layer = "play"
    this.el.dataset.layer = "play"
    this.setup = null
    if (this.palette) this.palette.hidden = true
    if (this.focused && ctx.layer === "setup") setLayer("normal")
    lines.load(this.key, { start: fen }, { undo: "Set up position" })
    this.refresh()
  }

  applyFen(fen) {
    const [placement, side = "w", castling = "-", ep = "-"] = fen.split(" ")
    Object.assign(this.setup, { side, castling, ep })
    this.cg.set({ fen: placement })
    this.onSetupChange()
  }

  // ── Move entry ───────────────────────────────────────────────────────────────────────────────────────────

  enterEntry() {
    if (!this.chess) return status("This position can't be played (a diagram)", { kind: "error" }) || false
    this.entry = { text: "", index: 0, candidates: [], previous: ctx.layer }
    this.layer = "entry"
    this.el.dataset.layer = "entry"
    ctx.overlay = "entry"
    setLayer("entry")
    setOverlayHandler((e, token) => this.onEntryKey(token))
    this.renderStrip()
  }

  leaveEntry() {
    if (!this.entry) return
    this.entry = null
    this.layer = "play"
    this.el.dataset.layer = "play"
    if (ctx.overlay === "entry") {
      ctx.overlay = null
      setOverlayHandler(null)
      setLayer("normal")
    }
    this.cg.setAutoShapes([])
    this.renderStrip()
  }

  onEntryKey(token) {
    const entry = this.entry
    if (token === "esc") return this.leaveEntry()
    if (token === "backspace") entry.text = entry.text.slice(0, -1)
    else if (token === "tab") entry.index = (entry.index + 1) % Math.max(1, entry.candidates.length)
    else if (token === "enter") return this.playEntry()
    else if (token.length === 1 && /[a-hA-H1-8KQRBNDTLSkqrnstlxXoO0=\-]/.test(token)) entry.text += token
    else return "fallthrough" // leader, focus keys … still work; the entry stays open
    const { candidates, exact } = matchMoves(entry.text, this.chess.moves({ verbose: true }))
    entry.candidates = candidates
    entry.exact = exact
    if (token !== "tab") entry.index = exact ? candidates.indexOf(exact) : 0
    this.cg.setAutoShapes(candidates.map((m, i) => ({ orig: m.from, dest: m.to, brush: i === entry.index ? "paleGreen" : "paleBlue" })))
    this.renderStrip()
  }

  playEntry() {
    const entry = this.entry
    const move = entry.exact || (entry.candidates.length === 1 ? entry.candidates[0] : null) || (entry.tabbed ? entry.candidates[entry.index] : null)
    if (!move) {
      if (entry.candidates.length > 1) {
        entry.tabbed = true
        return status(`Which one? ${entry.candidates.map((m) => m.san).join(" / ")} · ⇥ choose, ↵ play`, { timeout: 4000 })
      }
      return status(entry.text ? `No legal move matches “${entry.text}”` : "Type a move, e.g. Nf3, Sf3 or g1f3", { kind: "error", timeout: 3000 })
    }
    const chess = chessOf(lines.fenAt(this.line))
    lines.play(this.key, chess.move({ from: move.from, to: move.to, promotion: move.promotion }))
    Object.assign(entry, { text: "", index: 0, candidates: [], exact: null, tabbed: false })
    this.cg.setAutoShapes([])
    this.renderStrip()
  }

  // ── The strip under the board: what a click does, the state, problems ──────────────────────────────────

  renderStrip() {
    if (!this.strip) return
    const parts = []
    const line = this.line
    if (this.layer === "setup") {
      const s = this.setup
      const glyph = GLYPHS[s.color][s.role]
      const tool = { piece: `click: place ${glyph} ${s.color} · ⇧click: the other colour · right-click: empty`, eraser: "click: empty a square", hand: "drag: move pieces freely" }[s.tool]
      parts.push(text(tool), text(` · ${s.side === "w" ? "white" : "black"} to move · castling ${s.castling || "-"} · e.p. ${s.ep || "-"}${s.diagram ? " · diagram" : ""}`))
      const fen = span("board__fen mono", this.fullFen())
      parts.push(fen)
      const check = s.check
      if (check && !check.ok) {
        const problems = span(`board__problems${s.diagram ? "" : " is-error"}`, check.problems.map((p) => p.message).join(" · "))
        if (check.fixed) problems.append(text(" · a: fix"))
        parts.push(problems)
      }
      this.palette?.querySelectorAll("[data-cmd='board.piece']").forEach((b) => {
        b.setAttribute("aria-pressed", String(s.tool === "piece" && b.dataset.args === s.role))
        const icon = b.querySelector(".keybutton__icon")
        if (icon) icon.textContent = GLYPHS[s.color][b.dataset.args]
      })
      for (const [id, on] of [["board.eraser", s.tool === "eraser"], ["board.hand", s.tool === "hand"], ["board.diagram", s.diagram]]) {
        this.palette?.querySelector(`[data-cmd='${id}']`)?.setAttribute("aria-pressed", String(on))
      }
    } else if (this.layer === "entry") {
      const e = this.entry
      parts.push(text("Type a move: "), span("board__entry mono", `${e.text}▏`))
      if (e.candidates.length) parts.push(text(" · " + e.candidates.map((m, i) => (i === e.index ? `[${m.san}]` : m.san)).join(" ")))
      parts.push(text(" · ↵ play · ⇥ next · Esc done"))
    } else {
      const fen = lines.fenAt(line)
      parts.push(text(this.chess ? `${fen.split(" ")[1] === "b" ? "Black" : "White"} to move` : "Diagram: not playable"))
      parts.push(text(` · move ${line.ply} of ${line.moves.length}`))
      parts.push(text(this.squareTool ? " · right-click: fill a square (⇧ red · ⌥ blue)" : " · click/drag: move · right-drag: arrow (⇧ red · ⌥ blue · ⇧⌥ yellow)"))
    }
    this.strip.replaceChildren(...parts)
  }
}

const text = (t) => document.createTextNode(t)
function span(className, t) {
  const el = document.createElement("span")
  el.className = className
  el.textContent = t
  return el
}

// ── Mounting, sync, focus ─────────────────────────────────────────────────────────────────────────────────────

export function mountBoard(el) {
  el.board = new Board(el)
}

on("line", ({ key }) => {
  for (const board of boards) {
    if (!board.alive) {
      boards.delete(board)
      continue
    }
    if (board.key === key) board.refresh()
  }
  for (const view of document.querySelectorAll("[data-island='line-text']")) renderLineText(view)
})

on("layout", () => {
  for (const board of boards) if (board.alive) board.refresh()
  for (const view of document.querySelectorAll("[data-island='line-text']")) renderLineText(view)
})

on("focus", () => {
  for (const board of boards) {
    if (!board.alive) continue
    if (board.entry && !board.focused) board.leaveEntry()
  }
  const board = focusedBoard()
  if (board?.layer === "setup" && ctx.layer !== "setup") setLayer("setup")
  else if (!board && ctx.layer === "setup") setLayer("normal")
  else if (board && board.layer !== "setup" && ctx.layer === "setup") setLayer("normal")
})

on("theme", () => {
  requestAnimationFrame(() => {
    for (const board of boards) if (board.alive) board.cg.set({ drawable: { brushes: brushes() } })
  })
})

export function focusedBoard() {
  return ctx.pane?.el?.querySelector("[data-island='board']")?.board || null
}

/** The line key of the focused pane (a board or the PGN/FEN view). */
export function focusedKey() {
  const pane = ctx.pane?.el
  if (!pane) return null
  return lines.keyOf(pane.closest(".workspace").dataset.mode, nodeOf(pane) || { id: pane.dataset.pane })
}

// ── The PGN / FEN view ────────────────────────────────────────────────────────────────────────────────────────

export function renderLineText(el) {
  const pane = el.closest("[data-pane]")
  if (!pane?.isConnected) return
  const key = lines.keyOf(pane.closest(".workspace").dataset.mode, nodeOf(pane) || { id: pane.dataset.pane })
  const line = lines.getLine(key)
  el.querySelector("[data-line-fen]").textContent = lines.fenAt(line)
  el.querySelector("[data-line-pgn]").textContent = lines.pgnOf(line)
  const title = el.querySelector("[data-line-title]")
  if (title) title.textContent = line.title || ""
}

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

const withBoard = (fn) => (args) => {
  const board = focusedBoard()
  if (!board) return false
  return fn(board, args)
}

handle("board.flip", withBoard((b) => {
  b.orientation = b.orientation === "white" ? "black" : "white"
  b.cg.set({ orientation: b.orientation })
}))
handle("board.back", withBoard((b) => lines.goTo(b.key, b.line.ply - 1)))
handle("board.forward", withBoard((b) => lines.goTo(b.key, b.line.ply + 1)))
handle("board.start", withBoard((b) => lines.goTo(b.key, 0)))
handle("board.end", withBoard((b) => lines.goTo(b.key, b.line.moves.length)))
handle("board.squaretool", withBoard((b) => {
  b.squareTool = !b.squareTool
  b.renderStrip()
  status(b.squareTool ? "Square tool: right-click fills a square" : "Square tool off: right-drag draws arrows", { timeout: 2500 })
}))
handle("board.cleardrawings", withBoard((b) => {
  lines.setShapes(b.key, [])
  lines.setSquares(b.key, {})
}))
handle("board.entry", withBoard((b) => (b.entry ? b.leaveEntry() : b.enterEntry())))
handle("board.setup", withBoard((b) => (b.layer === "setup" ? b.leaveSetup() : b.enterSetup())))

async function copy(text, what) {
  try {
    await navigator.clipboard.writeText(text)
    status(`Copied ${what}`, { kind: "good", timeout: 2500 })
  } catch {
    status(`Could not copy the ${what}: the browser refused`, { kind: "error" })
  }
}
handle("board.copyfen", () => {
  const board = focusedBoard()
  const fen = board?.layer === "setup" ? board.fullFen() : lines.fenAt(lines.getLine(focusedKey()))
  return copy(fen, "FEN")
})
handle("board.copypgn", () => copy(lines.pgnOf(lines.getLine(focusedKey())), "PGN"))

// Setup commands (layer.setup)
const withSetup = (fn) => withBoard((b, args) => (b.layer === "setup" ? fn(b, b.setup, args) : false))
handle("board.piece", withSetup((b, s, [role]) => {
  Object.assign(s, { role: ROLE_OF[role] || role, tool: "piece" })
  b.renderStrip()
}))
handle("board.color", withSetup((b, s) => { s.color = s.color === "white" ? "black" : "white"; b.renderStrip() }))
handle("board.eraser", withSetup((b, s) => { s.tool = s.tool === "eraser" ? "piece" : "eraser"; b.renderStrip() }))
handle("board.hand", withSetup((b, s) => { s.tool = s.tool === "hand" ? "piece" : "hand"; b.renderStrip() }))
handle("board.clear", withSetup((b, s) => { s.castling = "-"; s.ep = "-"; b.cg.set({ fen: EMPTY }); b.onSetupChange() }))
handle("board.initial", withSetup((b) => b.applyFen(lines.START_FEN)))
handle("board.side", withSetup((b, s) => { s.side = s.side === "w" ? "b" : "w"; s.ep = "-"; b.onSetupChange() }))
handle("board.mirror", withSetup((b, s) => {
  const placement = b.cg.getFen().split("/").reverse().map((row) => row.replace(/[a-z]/gi, (c) => (c === c.toUpperCase() ? c.toLowerCase() : c.toUpperCase()))).join("/")
  const castling = s.castling === "-" ? "-" : [...s.castling].map((c) => (c === c.toUpperCase() ? c.toLowerCase() : c.toUpperCase())).sort((a, b) => "KQkq".indexOf(a) - "KQkq".indexOf(b)).join("")
  b.applyFen(`${placement} ${s.side === "w" ? "b" : "w"} ${castling} -`)
}))
handle("board.diagram", withSetup((b, s) => { s.diagram = !s.diagram; b.validate() }))
handle("board.fix", withSetup((b, s) => {
  if (!s.check?.fixed) return status("Nothing to fix automatically", { timeout: 2500 }) || false
  b.applyFen(s.check.fixed)
}))
handle("board.castling", withSetup(async (b, s) => {
  const rights = s.castling === "-" ? "" : s.castling
  const choice = await openMenu({
    title: "Castling rights",
    anchor: b.palette,
    items: [["K", "White O-O"], ["Q", "White O-O-O"], ["k", "Black O-O"], ["q", "Black O-O-O"]].map(([key, label]) => ({
      label: `${label} ${rights.includes(key) ? "✓" : ""}`, key, keys: [key], value: key,
    })),
  })
  if (!choice) return false
  const next = rights.includes(choice) ? rights.replace(choice, "") : rights + choice
  s.castling = [...next].sort((a, c) => "KQkq".indexOf(a) - "KQkq".indexOf(c)).join("") || "-"
  b.onSetupChange()
}))
handle("board.ep", withSetup(async (b, s) => {
  const pieces = b.cg.state.pieces
  const white = s.side === "w"
  const candidates = "abcdefgh".split("").filter((f) => {
    const pawn = pieces.get(`${f}${white ? 5 : 4}`)
    return pawn?.role === "pawn" && pawn.color === (white ? "black" : "white") && !pieces.get(`${f}${white ? 6 : 3}`) && !pieces.get(`${f}${white ? 7 : 2}`)
  }).map((f) => `${f}${white ? 6 : 3}`)
  const choice = await openMenu({
    title: "En passant square",
    anchor: b.palette,
    items: [{ label: "none", key: "0", keys: ["0"], value: "-" }, ...candidates.map((sq, i) => ({ label: sq, key: String(i + 1), keys: [String(i + 1)], value: sq }))],
  })
  if (!choice) return false
  s.ep = choice
  b.onSetupChange()
}))

// ── Piece set ─────────────────────────────────────────────────────────────────────────────────────────────────

const currentSet = () => (window.SPOS.tokens || {})["piece-set"] || "cburnett"

handle("board.pieces", async ([name]) => {
  const sets = window.SPOS.themes.pieces
  if (!name) {
    const names = Object.keys(sets)
    const keys = "123456789abcdefghijklmnopqrstuvwxyz"
    const before = currentSet()
    name = await openMenu({
      title: "Piece set · ↑↓ preview · ↵ keep · Esc back",
      anchor: focusedBoard()?.el || null,
      start: Math.max(0, names.indexOf(before)),
      onCursor: (value) => { if (value) document.documentElement.dataset.pieces = value },
      items: names.map((n, i) => ({ label: sets[n].label, note: `${sets[n].author} · ${sets[n].licence}`, key: keys[i], keys: [keys[i]], value: n })),
    })
    if (!name || name === before) {
      document.documentElement.dataset.pieces = before
      return false
    }
  }
  if (!sets[name]) return status(`No piece set '${name}'`, { kind: "error" }) || false
  return run("pref.set", [`piece-set=${name}`])
})

/** Mark the active set in the style guide's list. */
export function markPieceSet() {
  for (const el of document.querySelectorAll(".pieceset[data-args]")) el.setAttribute("aria-pressed", String(el.dataset.args === currentSet()))
}
on("theme", markPieceSet)
on("layout", markPieceSet)
