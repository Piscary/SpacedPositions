// The engine (spec 04 · Analyse · Engine): Stockfish 17.1 lite (WASM, one thread) in a worker. It follows the line
// of the analysis in the focused link group, shows MultiPV lines in Engine panes, draws its best moves on the
// boards and fills their eval bar. It runs only while Analyse is on screen and the tab is visible.

import { Chess } from "../../vendor/chess.js"
import { handle } from "./commands.js"
import { ctx, emit, on, status, storage } from "./context.js"
import * as lines from "./lines.js"
import { addLine, currentKey, treeOf } from "./analysis.js"

const WORKER = "/static/vendor/stockfish-17.1-lite-single-03e3232.js"
const DEPTH = 24
const SAN_PLIES = 14

let worker = null
let ready = false
let enabled = storage("engine.on") ?? false
let multipv = Number(storage("engine.lines")) || 3
let searching = false // a "go" is running; the next search waits for its bestmove
let queued = null // {key, fen} to search when the running one stops
let search = null // {key, fen, white, lines: [], depth, nps}

const engineKey = () => (ctx.mode === "analyse" ? currentKey() : null)

function start() {
  if (worker) return
  try {
    worker = new Worker(WORKER)
  } catch (err) {
    enabled = false
    return status(`The engine could not start: ${err.message}`, { kind: "error" })
  }
  worker.onmessage = (e) => onLine(String(e.data))
  worker.onerror = () => {
    status("The engine stopped with an error", { kind: "error" })
    stop()
  }
  send("uci")
  paint()
}

function stop() {
  worker?.terminate()
  worker = null
  ready = false
  searching = false
  queued = null
  if (search) emit("engine", { key: search.key, shapes: [], score: null })
  search = null
  paint()
}

const send = (cmd) => worker?.postMessage(cmd)

function onLine(text) {
  if (text === "uciok") {
    send(`setoption name MultiPV value ${multipv}`)
    send("isready")
  } else if (text === "readyok") {
    if (!ready) {
      ready = true
      follow()
    }
  } else if (text.startsWith("info ") && text.includes(" pv ")) {
    onInfo(text)
  } else if (text.startsWith("bestmove")) {
    searching = false
    if (queued) go(queued)
    paint()
  }
}

/** Analyse a position: stop the running search first, the next starts on its bestmove. */
function analyse(key, fen) {
  if (!ready) return
  if (search && search.key === key && search.fen === fen) return
  const next = { key, fen }
  if (search && search.key !== key) emit("engine", { key: search.key, shapes: [], score: null })
  search = { key, fen, white: fen.split(" ")[1] !== "b", lines: [], depth: 0, nps: 0 }
  emit("engine", { key, shapes: [], score: null })
  paint()
  if (searching) {
    queued = next
    send("stop")
  } else go(next)
}

function go({ fen }) {
  queued = null
  let legal = true
  try {
    legal = new Chess(fen).moves().length > 0
  } catch {
    legal = false // a diagram: nothing to search
  }
  if (!legal) return paint()
  searching = true
  send(`position fen ${fen}`)
  send(`go depth ${DEPTH}`)
}

function onInfo(text) {
  if (!search || queued || / (lowerbound|upperbound) /.test(text)) return
  const field = (name) => {
    const m = new RegExp(` ${name} (\\S+)`).exec(text)
    return m ? m[1] : null
  }
  const depth = Number(field("depth"))
  const index = Number(field("multipv") || 1) - 1
  const pv = text.split(" pv ")[1].trim().split(" ")
  const m = / score (cp|mate) (-?\d+)/.exec(text)
  if (!m) return
  const sign = search.white ? 1 : -1 // scores from white's side
  const score = m[1] === "cp" ? { cp: Number(m[2]) * sign } : { mate: Number(m[2]) * sign }
  score.text = scoreText(score)
  search.lines[index] = { depth, score, pv, san: sans(search.fen, pv) }
  search.depth = Math.max(search.depth, index === 0 ? depth : 0)
  search.nps = Number(field("nps")) || search.nps
  if (index === 0) {
    const best = search.lines.slice(0, multipv).filter(Boolean)
    const shapes = best.map((l, i) => ({ orig: l.pv[0].slice(0, 2), dest: l.pv[0].slice(2, 4), brush: i === 0 ? "paleBlue" : "paleGrey" }))
    emit("engine", { key: search.key, shapes: shapes.slice(0, 1).concat(shapes.slice(1).map((s) => ({ ...s, modifiers: { lineWidth: 6 } }))), score })
  }
  schedulePaint()
}

function scoreText(score) {
  if (score.mate !== undefined) return score.mate === 0 ? "#" : `${score.mate > 0 ? "+" : "−"}M${Math.abs(score.mate)}`
  const v = score.cp / 100
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}`
}

function sans(fen, pv) {
  const out = []
  try {
    const chess = new Chess(fen)
    for (const uci of pv.slice(0, SAN_PLIES)) {
      const move = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
      out.push({ uci, san: move.san, white: move.color === "w", number: Number(move.before.split(" ")[5]) })
    }
  } catch {
    // a stale line for another position: shown as far as it goes
  }
  return out
}

// ── Following the analysis ─────────────────────────────────────────────────────────────────────────────────────

function follow() {
  const running = enabled && ctx.mode === "analyse" && document.visibilityState === "visible"
  if (!running) {
    if (worker) stop()
    return paint()
  }
  if (!worker) return start()
  const key = engineKey()
  if (key) analyse(key, lines.fenAt(lines.getLine(key)))
}

on("line", ({ key }) => { if (enabled && key === engineKey()) follow() })
on("mode", () => follow())
on("layout", () => follow()) // also the first render after a reload
on("focus", () => { if (enabled) follow() })
document.addEventListener("visibilitychange", () => follow())

// ── Engine panes ───────────────────────────────────────────────────────────────────────────────────────────────

let paintTimer
function schedulePaint() {
  if (!paintTimer) paintTimer = setTimeout(() => { paintTimer = null; paint() }, 100)
}

function panes() {
  return [...document.querySelectorAll("#ws-analyse [data-island='engine']")]
}

function paint() {
  for (const el of panes()) {
    const stateEl = el.querySelector("[data-engine-state]")
    const info = el.querySelector("[data-engine-info]")
    const list = el.querySelector("[data-engine-lines]")
    stateEl.textContent = !enabled ? "off" : !ready ? "starting…" : searching ? "thinking" : "done"
    stateEl.dataset.state = !enabled ? "off" : searching || !ready ? "busy" : "on"
    info.textContent = enabled && search ? `Stockfish 17.1 · depth ${search.depth}/${DEPTH} · ${multipv} line${multipv > 1 ? "s" : ""}${search.nps ? ` · ${Math.round(search.nps / 1000)} kn/s` : ""}` : ""
    list.replaceChildren(...(enabled && search ? search.lines.slice(0, multipv).filter(Boolean).map(lineRow) : [hint()]))
  }
}

function hint() {
  const p = document.createElement("p")
  p.className = "muted engine__off"
  p.textContent = enabled ? "Waiting for a position…" : "The engine is off. e turns it on; it runs in this browser and stops when you leave Analyse."
  return p
}

function lineRow(line, i) {
  const row = document.createElement("div")
  row.className = "engine__line"
  row.dataset.line = i
  const score = document.createElement("span")
  score.className = `engine__score${line.score.cp > 0 || line.score.mate > 0 ? " is-white" : ""}`
  score.textContent = line.score.text
  const moves = document.createElement("span")
  moves.className = "engine__moves"
  line.san.forEach((m, j) => {
    if (m.white || j === 0) moves.append(Object.assign(document.createElement("span"), { className: "mt-num", textContent: `${m.number}${m.white ? "." : "…"}` }))
    const b = document.createElement("span")
    b.className = "engine__move"
    b.textContent = m.san
    b.dataset.ply = j
    b.title = "Add the line up to this move to the analysis"
    moves.append(b, " ")
  })
  row.append(score, moves)
  return row
}

export function mountEngine(el) {
  paint()
  el.addEventListener("click", (e) => {
    const move = e.target.closest(".engine__move")
    if (!move || !search) return
    const line = search.lines[Number(move.closest("[data-line]").dataset.line)]
    if (line) addToAnalysis(line.pv.slice(0, Number(move.dataset.ply) + 1))
  })
}

function addToAnalysis(ucis) {
  const key = search.key
  if (treeOf(key)) return addLine(key, ucis)
  // A board without an analysis: the moves go onto its line.
  let fen = search.fen
  const chess = new Chess(fen)
  for (const uci of ucis) {
    const move = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
    lines.play(key, move)
    fen = move.after
  }
}

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

handle("engine.toggle", () => {
  enabled = !enabled
  storage("engine.on", enabled)
  status(enabled ? "Engine on: Stockfish 17.1 in this browser" : "Engine off", { timeout: 2000 })
  follow()
})

handle("engine.best", () => {
  const best = search?.lines[0]
  if (!best) return status("The engine has no move yet", { timeout: 2000 }) || false
  addToAnalysis(best.pv.slice(0, 1))
})

handle("engine.lines", ([count]) => {
  const n = Number(count) || (multipv % 5) + 1
  multipv = n
  storage("engine.lines", n)
  status(`Engine: ${n} line${n > 1 ? "s" : ""}`, { timeout: 1500 })
  if (!worker) return paint()
  send(`setoption name MultiPV value ${n}`) // read by the next "go"
  if (search) {
    const { key, fen } = search
    search = null
    analyse(key, fen) // restarts the search
  }
})

Object.assign((window.SPOS ||= {}), { engine: { ready: () => ready && Boolean(search?.lines[0]), state: () => ({ enabled, ready, searching, search }) } })
