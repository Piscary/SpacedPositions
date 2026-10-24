// The trainer (spec 04 · Train, 09 §7): Launcher → Solving → Feedback → Result. Puzzles arrive in batches, moves
// are judged here against the solution tree (training/puzzles.py has the same rules), attempts are posted in the
// background: nothing in the solve → next loop waits for the network.

import { Chess } from "../../vendor/chess.js"
import { handle, run } from "../core/commands.js"
import { ctx, on, status, storage, updateStatus } from "../core/context.js"
import { setOverlayHandler } from "../core/keys.js"
import { focusPane, switchMode } from "../core/layout.js"
import * as lines from "../core/lines.js"
import { trainBoard } from "./board.js"

const REPLY_MS = 280
const BATCH_LEFT = 5
const DEFAULT_CUSTOM = { mode: "review", look: "normal", side: "move", lives: "0", first: false, filter: "" }

const T = {
  el: null,
  state: "launcher",
  session: null, // the start response
  params: null, // what started it (for "again")
  queue: [],
  offset: 0,
  fetching: null,
  current: null,
  token: 0, // bumps on every new puzzle: late replies and timers of an old one are ignored
  results: [],
  solved: 0,
  failed: 0,
  combo: 0,
  bestCombo: 0,
  streak: 0,
  lives: 0,
  clock: null, // Storm: {deadline, timer, started}
  paused: null,
  custom: { ...DEFAULT_CUSTOM, ...(storage("train.custom") || {}) },
}

window.SPOS ||= {}
window.SPOS.train = {
  start: (params) => start(params),
  hasLast: () => Boolean(T.params || lastFromLauncher()),
  hasMissed: () => T.results.some((r) => !r.success && !r.retry),
  // read-only views for the journey tests and the status line
  puzzle: () => (T.current ? { ...T.current.p, at: T.current.at, onLine: T.current.onLine } : null),
  state: () => ({ state: T.state, solved: T.solved, failed: T.failed, combo: T.combo, streak: T.streak, lives: T.lives, results: T.results.length }),
}

const $ = (sel) => T.el?.querySelector(sel)
const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) })

// ── States ─────────────────────────────────────────────────────────────────────────────────────────────────────

function setState(state) {
  T.state = state
  ctx.trainState = state
  for (const [name, sel] of [["launcher", "[data-train-launcher]"], ["solving", "[data-train-hud]"], ["feedback", "[data-train-feedback]"], ["result", "[data-train-result]"]]) {
    const el = $(sel)
    if (el) el.hidden = name !== state
  }
  document.getElementById("shell").classList.toggle("is-solving", state === "solving" || state === "feedback")
  updateStatus()
  renderCustom()
}

export function mountTrain(el) {
  T.el = el
  setState(T.session && T.state !== "launcher" ? T.state : "launcher")
}

function lastFromLauncher() {
  const script = T.el?.querySelector("[data-again]")
  try {
    return script ? JSON.parse(script.textContent) : null
  } catch {
    return null
  }
}

// ── Starting ───────────────────────────────────────────────────────────────────────────────────────────────────

async function start(params) {
  if (T.state === "solving" || T.state === "feedback") await finish({ quiet: true })
  if (ctx.mode !== "train") await switchMode("train")
  const board = trainBoard()
  if (!board) return status("Train needs a board pane: ␣ w v, then b", { kind: "error" }) || false
  const response = await post("/train/start/", params).catch(() => null)
  const data = response ? await response.json().catch(() => null) : null
  if (!data) return status("Could not start: the app is not reachable", { kind: "error" }) || false
  if (!data.ok) return status(data.message || "Could not start", { kind: data.empty ? "info" : "error" }) || false
  Object.assign(T, {
    session: data,
    params,
    queue: data.puzzles,
    offset: data.puzzles.length,
    results: [],
    solved: 0,
    failed: 0,
    combo: 0,
    bestCombo: 0,
    streak: 0,
    lives: Number(data.options.lives || 0),
    paused: null,
  })
  $("[data-hud-label]").textContent = data.label
  $("[data-hud-clock]").hidden = data.mode !== "storm"
  $("[data-hud-combo]").hidden = data.mode !== "storm"
  $("[data-hud-lives]").hidden = data.mode !== "streak" || !T.lives
  if (data.mode === "storm") startClock(Number(data.options.minutes || 3) * 60000)
  setState("solving")
  focusPane(board.pane.dataset.pane)
  nextPuzzle()
}

handle("train.review", () => start({ mode: "review", look: "normal", side: "move" }))
handle("train.storm", ([minutes]) => start({ mode: "storm", minutes: Number(minutes || 3), look: "normal", side: "move", pace: "medium" }))
handle("train.streak", ([lives, look]) => start({ mode: "streak", lives: Number(lives || 0), look: look || "normal", side: "move" }))
handle("train.again", () => {
  const params = T.params || lastFromLauncher()
  if (!params) return false
  return start({ ...params, cards: undefined })
})
handle("train.custom", () => {
  const c = T.custom
  return start({ mode: c.mode, look: c.look, side: c.side, lives: Number(c.lives), first_move: c.first, minutes: 3, pace: "medium", filter: c.filter })
})
handle("train.set", ([option, value]) => {
  if (option === "first") T.custom.first = !T.custom.first
  else T.custom[option] = value
  storage("train.custom", T.custom)
  renderCustom()
})

// The filter of a custom session: a Library query (spec 11 §3); the chips put in a saved query.
document.addEventListener("input", (e) => {
  if (!e.target.matches?.("[data-train-filter]")) return
  T.custom.filter = e.target.value
  storage("train.custom", T.custom)
  countMatches()
})

let matchTimer
function countMatches() {
  clearTimeout(matchTimer)
  matchTimer = setTimeout(async () => {
    const el = T.el?.querySelector("[data-train-match]")
    if (!el) return
    const data = await post("/lib/cards/", { c: "puzzles", q: T.custom.filter || "", count: true }).then((r) => r.json()).catch(() => null)
    el.textContent = data ? `${data.count} card${data.count === 1 ? "" : "s"} match` : ""
  }, 250)
}
document.addEventListener("click", (e) => {
  const chip = e.target.closest?.("[data-train-query]")
  if (!chip) return
  T.custom.filter = chip.dataset.trainQuery
  storage("train.custom", T.custom)
  renderCustom()
})

function renderCustom() {
  const box = T.el?.querySelector("[data-custom]")
  if (!box) return
  const field = box.querySelector("[data-train-filter]")
  if (field && document.activeElement !== field) field.value = T.custom.filter || ""
  countMatches()
  for (const el of box.querySelectorAll("[data-cmd='train.set']")) {
    const [option, value] = el.dataset.args.split(" ")
    if (option === "first") el.setAttribute("aria-pressed", String(T.custom.first))
    else el.setAttribute("aria-checked", String(String(T.custom[option]) === value))
  }
}

// ── Puzzles ────────────────────────────────────────────────────────────────────────────────────────────────────

function refill() {
  if (T.fetching || T.offset >= T.session.total) return T.fetching
  T.fetching = fetch(`/train/r/${T.session.session}/batch/?offset=${T.offset}`)
    .then((r) => r.json())
    .then((data) => {
      T.queue.push(...data.puzzles)
      T.offset += data.puzzles.length || 10
    })
    .catch(() => {})
    .finally(() => { T.fetching = null })
  return T.fetching
}

async function nextPuzzle() {
  if (!T.queue.length) await refill()
  const p = T.queue.shift()
  if (!p) return finish()
  if (T.queue.length < BATCH_LEFT) refill()
  const board = trainBoard()
  const token = ++T.token
  const orientation = p.solver === "b" ? "black" : "white"
  T.current = { p, token, point: p.tree, onLine: true, at: 0, hinted: 0, wrong: "", gaveUp: false, t0: performance.now(), pausedMs: 0, fen: p.fen }
  board.startSolving({ fen: p.fen, orientation, look: T.session.options.look, onMove: (move) => onMove(move, token) })
  renderHud()
  setState("solving")
}

function chessAt(fen) {
  try {
    return new Chess(fen)
  } catch {
    return null
  }
}

/** Judge a solver move. Returns "ok" (played) or "wrong" (the board snaps back). */
function onMove(move, token) {
  const c = T.current
  if (!c || c.token !== token || T.state !== "solving" || T.paused) return "wrong"
  const uci = move.from + move.to + (move.promotion || "")
  let option = c.point.moves.find((o) => o.uci === uci)
  if (!option && move.san.endsWith("#")) {
    // any mating move counts when the main move mates
    const check = chessAt(move.before)
    const main = c.point.moves[0].uci
    const mainMove = check?.move({ from: main.slice(0, 2), to: main.slice(2, 4), promotion: main[4] })
    if (mainMove?.san.endsWith("#")) option = { uci, replies: [] }
  }
  const key = trainBoard().key
  if (!option) {
    miss({ wrong: uci })
    return "wrong"
  }
  lines.play(key, move)
  const following = c.onLine && c.p.line[c.at] === uci
  if (!option.replies?.length) {
    solved()
    return "ok"
  }
  let reply = option.replies[0]
  if (following) reply = option.replies.find((r) => r.uci === c.p.line[c.at + 1]) || reply
  c.onLine = following && reply.uci === c.p.line[c.at + 1]
  c.at += 2
  setTimeout(() => {
    if (T.current?.token !== token) return
    const chess = chessAt(move.after)
    const answer = chess?.move({ from: reply.uci.slice(0, 2), to: reply.uci.slice(2, 4), promotion: reply.uci[4] })
    if (!answer) return miss({ wrong: "" })
    lines.play(key, answer)
    c.point = reply.next
    trainBoard().refresh()
  }, REPLY_MS)
  return "ok"
}

function elapsed(c) {
  return Math.round(performance.now() - c.t0 - c.pausedMs)
}

function solved() {
  const c = T.current
  const ms = elapsed(c)
  const success = !c.hinted
  trainBoard().flash("good")
  record(c, success, ms)
  if (c.p.retry) return feedback(c, success, ms)
  if (success) {
    T.solved++
    T.combo++
    T.streak++
  } else {
    T.failed++
    T.combo = 0
  }
  T.bestCombo = Math.max(T.bestCombo, T.combo)
  renderHud()
  if (T.session.mode === "storm") {
    if (success) addTime(bonus())
    T.current = null
    return setTimeout(nextPuzzle, 150)
  }
  feedback(c, success, ms)
}

function miss({ wrong = "", gaveUp = false }) {
  const c = T.current
  if (!c) return
  c.wrong = wrong
  c.gaveUp = gaveUp
  const ms = elapsed(c)
  record(c, false, ms)
  if (c.p.retry) return feedback(c, false, ms)
  T.failed++
  T.combo = 0
  if (T.session.mode === "storm") {
    renderHud()
    trainBoard().flash("bad")
    addTime(-T.session.clock.penalty)
    T.current = null
    return setTimeout(nextPuzzle, 250)
  }
  if (T.session.mode === "streak") {
    if (T.lives > 0) {
      T.lives--
      const lives = $("[data-hud-lives]")
      lives.classList.remove("is-hit")
      void lives.offsetWidth
      lives.classList.add("is-hit")
    } else T.over = true
  }
  renderHud()
  feedback(c, false, ms)
}

function record(c, success, ms) {
  if (c.p.retry) {
    $("[data-hud-last]").textContent = `${success ? "✓" : "✗"} retry (not scored) · ${(ms / 1000).toFixed(1)}s`
    T.results.push({ card: c.p.card, success, ms, retry: true, reply: Promise.resolve(null) })
    return
  }
  const body = {
    card: c.p.card,
    success,
    ms,
    hinted: c.hinted > 0,
    gave_up: c.gaveUp,
    wrong_move: c.wrong,
    solved_as: c.p.solver,
    mirrored: c.p.mirrored,
    flipped: trainBoard()?.orientation !== (c.p.solver === "b" ? "black" : "white"),
  }
  T.results.push({ card: c.p.card, success, ms, title: c.p.title, fen: c.p.fen })
  const result = T.results.at(-1)
  result.reply = post(`/train/r/${T.session.session}/attempt/`, body)
    .then((r) => r.json())
    .catch(() => null)
  $("[data-hud-last]").textContent = `${success ? "✓" : "✗"} ${c.p.title || "Puzzle"} · ${(ms / 1000).toFixed(1)}s`
  renderHud()
}

// ── Heads-up display ───────────────────────────────────────────────────────────────────────────────────────────

const LETTER = { k: "K", q: "Q", r: "R", b: "B", n: "N", p: "" }

function pieceList(fen) {
  const chess = chessAt(fen)
  if (!chess) return ""
  const out = { w: [], b: [] }
  for (const row of chess.board()) for (const sq of row) if (sq) out[sq.color].push(`${LETTER[sq.type]}${sq.square}`)
  const rank = (piece) => ("KQRBN".includes(piece[0]) ? "KQRBN".indexOf(piece[0]) : 5) // pawns last
  const order = (list) => list.sort((a, b) => rank(a) - rank(b))
  return `White: ${order(out.w).join(" ")}\nBlack: ${order(out.b).join(" ")}`
}

function renderHud() {
  if (!T.session || !T.el) return
  const c = T.current
  $("[data-hud-solved]").textContent = T.session.mode === "streak" ? T.streak : T.solved
  $("[data-hud-failed]").textContent = T.failed
  $("[data-hud-progress]").textContent = T.session.mode === "review" ? `${T.results.length + (c ? 1 : 0)} / ${T.session.total}` : ""
  if (T.session.mode === "streak") $("[data-hud-lives]").textContent = "♥".repeat(T.lives) + "♡".repeat(Math.max(0, Number(T.session.options.lives || 0) - T.lives))
  if (T.session.mode === "storm") {
    const clock = T.session.clock
    const level = clock.levels.reduce((lvl, need, i) => (T.combo >= need ? i : lvl), 0)
    const next = clock.levels[level + 1]
    $("[data-hud-combo-level]").textContent = `×${level + 1} combo · +${(bonus() / 1000).toFixed(1)}s a puzzle`
    $("[data-hud-combo-next]").textContent = next ? `${T.combo} → ${next}` : `${T.combo}`
    const from = clock.levels[level]
    $("[data-hud-combo-fill]").style.width = `${next ? (100 * (T.combo - from)) / (next - from) : 100}%`
  }
  if (c) {
    const look = T.session.options.look
    $("[data-hud-side]").textContent = `${c.p.solver === "b" ? "Black" : "White"} to play`
    $("[data-hud-objective]").textContent = c.p.objective || (c.p.firstOnly ? "Find the first move" : "Find the best continuation")
    $("[data-hud-pieces]").hidden = look !== "blind"
    if (look === "blind") $("[data-hud-pieces]").textContent = pieceList(c.p.fen)
  }
  if (ctx.pane) ctx.pane.subject = `${T.session.label} · ${T.solved} solved${T.session.mode === "streak" && T.lives ? ` · ♥${T.lives}` : ""}`
  updateStatus()
}

// ── Storm clock ────────────────────────────────────────────────────────────────────────────────────────────────

function bonus() {
  const clock = T.session?.clock
  if (!clock) return 0
  const level = clock.levels.reduce((lvl, need, i) => (T.combo >= need ? i : lvl), 0)
  return clock.typical * clock.factor * clock.mult[level]
}

function startClock(ms) {
  stopClock()
  T.clock = { deadline: performance.now() + ms, started: performance.now() }
  T.clock.timer = setInterval(tick, 100)
  tick()
}

function stopClock() {
  if (T.clock) clearInterval(T.clock.timer)
}

function addTime(ms) {
  if (!T.clock) return
  T.clock.deadline += ms
  const delta = $("[data-hud-delta]")
  delta.textContent = `${ms >= 0 ? "+" : "−"}${Math.abs(ms / 1000).toFixed(1)}s`
  delta.className = `train__delta is-shown ${ms >= 0 ? "is-good" : "is-bad"}`
  clearTimeout(T.clock.deltaTimer)
  T.clock.deltaTimer = setTimeout(() => delta.classList.remove("is-shown"), 800)
  tick()
}

function tick() {
  if (!T.clock) return
  const left = Math.max(0, T.clock.deadline - performance.now())
  const s = Math.ceil(left / 1000)
  $("[data-hud-time]").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
  $("[data-hud-clock]").classList.toggle("is-low", left < 30000)
  if (left <= 0) {
    stopClock()
    finish()
  }
}

// ── Hints, giving up ───────────────────────────────────────────────────────────────────────────────────────────

handle("train.hint", () => {
  const c = T.current
  if (!c) return false
  c.hinted++
  const uci = c.onLine ? c.p.line[c.at] : c.point.moves[0].uci
  const shapes = [{ orig: uci.slice(0, 2), brush: "paleGreen" }]
  if (c.hinted > 1) shapes.push({ orig: uci.slice(0, 2), dest: uci.slice(2, 4), brush: "paleGreen" })
  trainBoard().hint(shapes)
  status(c.hinted > 1 ? "The move is on the board · this puzzle counts as missed" : "The piece to move is circled · this puzzle counts as missed", { timeout: 3000 })
})

handle("train.giveup", () => {
  if (!T.current) return false
  miss({ gaveUp: true })
})

// ── Feedback (Review, Streak) ──────────────────────────────────────────────────────────────────────────────────

function sanLine(fen, ucis) {
  const chess = chessAt(fen)
  if (!chess) return []
  const out = []
  for (const uci of ucis) {
    const m = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] })
    if (!m) break
    out.push(m)
  }
  return out
}

function moveText(fen, moves) {
  const [, side, , , , full] = fen.split(" ")
  let n = Number(full) || 1
  let white = side !== "b"
  return moves.map((m, i) => {
    const prefix = white ? `${n}.` : i === 0 ? `${n}…` : ""
    if (!white) n++
    white = !white
    return `${prefix}${m.san}`
  })
}

function feedback(c, success, ms) {
  const board = trainBoard()
  board.stopSolving()
  const key = board.key
  // The board shows the solution: after a miss it plays it through; after a solve it stays where the solver ended.
  const solution = c.p.line
  if (!success) {
    lines.load(key, { start: c.p.fen, moves: solution }, { undo: null, persist: false })
    lines.goTo(key, 0)
    autoplay(key, c.token)
  }
  T.current = { ...c, done: true }
  const verdict = $("[data-fb-verdict]")
  verdict.textContent = success ? `✓ Solved · ${(ms / 1000).toFixed(1)}s` : c.gaveUp ? "✗ Solution shown" : c.hinted ? `✓ Solved with a hint · counts as missed` : `✗ Missed${c.wrong ? ` (${c.wrong.slice(0, 2)}–${c.wrong.slice(2, 4)} was not it)` : ""}`
  verdict.className = `train__verdict ${success ? "is-good" : "is-bad"}`
  const schedule = $("[data-fb-schedule]")
  schedule.textContent = "…"
  T.results.at(-1).reply?.then((data) => {
    if (!data || T.current?.token !== c.token) return
    schedule.textContent = data.counted ? `next ${data.due} · ${data.stage}` : `solved before it was due: the schedule stays (next ${data.due})`
  })
  renderSolution(c, key)
  const tags = $("[data-fb-tags]")
  tags.replaceChildren(...(c.p.tags || []).map((t) => Object.assign(document.createElement("span"), { className: "chip chip--tag", textContent: t })))
  $("[data-fb-title]").textContent = c.p.title || ""
  $("[data-fb-source]").textContent = c.p.source || ""
  if (T.session.mode === "streak" && T.over) $("[data-fb-schedule]").textContent += " · the run is over: ↵ shows the result"
  setState("feedback")
}

function renderSolution(c, key) {
  const moves = sanLine(c.p.fen, c.p.line)
  const ply = lines.getLine(key).ply
  const box = $("[data-fb-solution]")
  box.replaceChildren(...moveText(c.p.fen, moves).flatMap((t, i) => [Object.assign(document.createElement("span"), { textContent: t, className: i === ply - 1 ? "is-here" : "" }), " "]))
}

function autoplay(key, token) {
  const step = () => {
    if (T.current?.token !== token || T.state !== "feedback" || T.current.stopAuto) return
    const line = lines.getLine(key)
    if (line.ply >= line.moves.length) return
    lines.goTo(key, line.ply + 1)
    renderSolution(T.current, key)
    setTimeout(step, 700)
  }
  setTimeout(step, 600)
}

handle("train.replay", ([step]) => {
  const board = trainBoard()
  if (!board || !T.current) return false
  T.current.stopAuto = true
  const line = board.line
  if (line.moves.length === 0 || line.start !== T.current.p.fen) lines.load(board.key, { start: T.current.p.fen, moves: T.current.p.line }, { undo: null, persist: false })
  lines.goTo(board.key, board.line.ply + (step === "back" ? -1 : 1))
  renderSolution(T.current, board.key)
})

handle("train.next", () => {
  if (T.state !== "feedback") return false
  if (T.over) return finish()
  nextPuzzle()
})

handle("train.retry", () => {
  if (T.state !== "feedback" || !T.current) return false
  const p = T.current.p
  T.queue.unshift({ ...p, retry: true })
  nextPuzzle()
})

// Analyse the puzzle's position at the move where the puzzle starts; Edit also opens its puzzle section.
async function openInAnalyse(edit) {
  if (T.state === "result") return run("list.open") // the puzzle under the result list's cursor, n / N for the others
  const p = T.current?.p
  if (!p) return false
  await window.SPOS.analysis.open(p.position, { node: p.startNode })
  if (edit) window.SPOS.analysis.focusInspector("z")
}
handle("train.analyse", () => openInAnalyse(false))
handle("train.edit", () => openInAnalyse(true))

handle("train.flag", async () => {
  if (!T.current) return false
  const r = await post("/train/flag/", { puzzle: T.current.p.puzzle }).then((x) => x.json()).catch(() => null)
  status(r?.ok ? "Flagged as broken: you'll find it in the library (phase 4)" : "Could not flag it", { kind: r?.ok ? "good" : "error" })
})

// ── Ending, result ─────────────────────────────────────────────────────────────────────────────────────────────

async function finish({ quiet = false } = {}) {
  if (!T.session) return
  stopClock()
  const board = trainBoard()
  board?.stopSolving()
  T.current = null
  T.over = false
  const session = T.session
  const duration = T.clock ? Math.round((performance.now() - T.clock.started) / 1000) : Math.round(T.results.reduce((a, r) => a + r.ms, 0) / 1000)
  T.clock = null
  await Promise.all(T.results.map((r) => r.reply))
  await post(`/train/r/${session.session}/end/`, { best_combo: T.bestCombo, streak: T.streak, duration_s: duration }).catch(() => null)
  if (quiet) {
    setState("launcher")
    return
  }
  const html = await fetch(`/train/r/${session.session}/result/`).then((r) => r.text()).catch(() => "")
  const box = $("[data-train-result]")
  box.innerHTML = html
  window.htmx?.process(box)
  setState("result")
  focusPane(T.el.closest("[data-pane]").dataset.pane)
}

handle("train.quit", () => finish())

handle("train.launcher", async () => {
  const html = await fetch("/train/launcher/").then((r) => r.text()).catch(() => null)
  if (html) $("[data-train-launcher]").innerHTML = html
  T.session = null
  setState("launcher")
})

handle("train.analysemissed", () => {
  // The result's rows marked missed, as Analyse's subject list.
  const rows = [...(T.el?.querySelectorAll("[data-train-result] [data-row][data-position]") || [])].filter((r) => r.querySelector(".result__mark.is-bad"))
  const ids = [...new Set(rows.map((r) => r.dataset.position))]
  if (!ids.length) return false
  return window.SPOS.analysis.open(ids[0], { node: Number(rows[0].dataset.node) || null, list: { ids, index: 0 } })
})

handle("train.missed", () => {
  const cards = [...new Set(T.results.filter((r) => !r.success && !r.retry).map((r) => r.card))]
  if (!cards.length) return false
  return start({ mode: "review", cards, look: T.session?.options.look || "normal", side: "move" })
})

handle("train.copy", async () => {
  const box = $("[data-train-result]")
  const text = [box.querySelector(".result__label")?.textContent, ...[...box.querySelectorAll(".stat")].map((s) => `${s.querySelector(".stat__label").textContent}: ${s.querySelector(".stat__value").textContent}`)].join(" · ")
  try {
    await navigator.clipboard.writeText(text)
    status("Copied the result", { kind: "good", timeout: 2500 })
  } catch {
    status("The browser didn't allow copying", { kind: "error" })
  }
})

// ── Pause (Esc while solving) ──────────────────────────────────────────────────────────────────────────────────

/** Called by layer.escape when nothing else is open. Returns true if it handled Esc. */
window.SPOS.trainEscape = () => {
  if (ctx.mode !== "train" || !["solving", "feedback"].includes(T.state)) return false
  if (T.state === "feedback") {
    offer("↵ next puzzle · q end the session and see the result", { enter: () => run("train.next"), q: () => finish() })
    return true
  }
  if (T.session.mode === "storm") {
    offer("Quit the Storm? y / n", { y: () => finish(), n: () => {} })
    return true
  }
  T.paused = performance.now()
  offer("Paused · ↵ resume · q quit · r restart", {
    enter: resume,
    q: () => finish(),
    r: () => { T.paused = null; start(T.params) },
  })
  return true
}

function resume() {
  if (T.paused && T.current) T.current.pausedMs += performance.now() - T.paused
  T.paused = null
}

function offer(text, actions) {
  status(text, { timeout: 0 })
  ctx.overlay = "pause"
  setOverlayHandler((e, token) => {
    const action = actions[token]
    if (!action && token !== "esc") return
    ctx.overlay = null
    setOverlayHandler(null)
    status("", { timeout: 1 })
    if (action) action()
    else if (T.paused) resume()
  })
}

// Leaving Train while solving pauses Review and Streak (a Storm keeps running: it's a race).
on("mode", ({ mode }) => {
  if (mode !== "train" && T.state === "solving" && T.session?.mode !== "storm" && !T.paused) T.paused = performance.now()
  if (mode === "train" && T.paused && ctx.overlay !== "pause") resume()
})
