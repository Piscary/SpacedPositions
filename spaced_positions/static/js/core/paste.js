// Paste anything anywhere (spec 06 §6): ⌘V outside a text field, `:paste`, or the PGN/FEN view's field. The server
// says what the text is (FEN, several FENs, PGN, lichess link); the status line offers what fits, each offer with
// its key: b show on a board, a analyse, c collect, i import.

import { focusedBoard, focusedKey } from "../islands/board.js"
import { analyseNew } from "./analysis.js"
import { collectPaste } from "./collect.js"
import { chooseFile, openImport } from "./importer.js"
import { command, enabled, handle, run } from "./commands.js"
import { ctx, keycaps, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { nodeOf } from "./layout.js"
import * as lines from "./lines.js"
import { tr, trn } from "./i18n.js"

let detected = null // the last detected paste, for the offer commands
let pasted = "" // its text (the import reads it again)

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

export async function detect(text) {
  pasted = text
  let result
  try {
    result = await fetch("/chess/paste/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ text }),
    }).then((r) => r.json())
  } catch {
    return status(tr("Paste: the app is not reachable"), { kind: "error" })
  }
  if (!["fen", "fens", "pgn"].includes(result.kind)) return status(tr("Paste: {message}", { message: result.message }), { kind: "error" })
  detected = result
  offer(result)
}

function describe(result) {
  if (result.kind === "fen") {
    const side = result.fen.split(" ")[1] === "b" ? tr("black to move") : tr("white to move")
    const problems = result.check.ok ? "" : ` · ${tr("not legal: {problems}", { problems: result.check.problems.map((p) => p.message).join(", ") })}`
    return `${result.source === "FEN" ? "FEN" : tr("Lichess position")} · ${side}${problems}`
  }
  if (result.kind === "fens") return `${trn("{n} FEN", "{n} FENs", result.fens.length)}${result.bad ? ` (${tr("{n} not legal", { n: result.bad })})` : ""}`
  const games = result.games > 1 ? ` · ${tr("{n} games (the first is shown)", { n: result.games })}` : ""
  return `PGN · ${result.title} · ${trn("{n} move", "{n} moves", result.moves.length)}${games}`
}

const OFFERS = [
  ["b", "paste.board"],
  ["a", "paste.analyse"],
  ["c", "paste.collect"],
  ["i", "paste.import"],
]

function offer(result) {
  const el = document.getElementById("status-message")
  status(describe(result), { timeout: 0 })
  const shown = OFFERS.filter(([, id]) => id !== "paste.import" || result.kind !== "fen")
  for (const [key, id] of shown) {
    const hint = document.createElement("span")
    hint.className = `keyhint${enabled(id).ok ? "" : " muted"}`
    hint.dataset.cmd = id
    hint.title = enabled(id).ok ? command(id).title : enabled(id).reason
    hint.append(keycaps([key]), ` ${command(id).title.replace(/^Paste: /, "")}`)
    el.append(" ", hint)
  }
  el.append(" ", keycaps(["esc"]))
  setOverlayHandler((e, token) => {
    const chosen = shown.find(([key]) => key === token)
    if (token === "esc" || chosen) {
      dismiss()
      if (chosen) run(chosen[1])
      return
    }
    dismiss()
    return "fallthrough" // any other key closes the offer and does what it always does
  })
  ctx.overlay = "offer"
}

function dismiss() {
  if (ctx.overlay !== "offer") return
  ctx.overlay = null
  setOverlayHandler(null)
  status("", { timeout: 1 })
}

/** The line a paste goes to: the focused board or PGN view, else a board in the focused pane's group, else any. */
function targetKey() {
  const pane = ctx.pane?.el
  const view = pane?.dataset.view
  if (view === "board" || view === "pgn") return focusedKey()
  const boardsHere = [...document.querySelectorAll(".workspace:not([hidden]) [data-view='board']")]
  const group = ctx.pane?.group
  const preferred = boardsHere.find((b) => group && nodeOf(b)?.group === group) || boardsHere[0]
  if (!preferred) return null
  const mode = preferred.closest(".workspace").dataset.mode
  return lines.keyOf(mode, nodeOf(preferred))
}

handle("paste.detect", async () => {
  let text
  try {
    text = await navigator.clipboard.readText()
  } catch {
    return status(tr("The browser didn't allow reading the clipboard: press ⌘V instead"), { kind: "error" }) || false
  }
  return detect(text)
})

handle("paste.board", async () => {
  if (!detected) return false
  let key = targetKey()
  if (!key) {
    await run("pane.split.vertical", ["board"])
    key = focusedKey()
  }
  if (detected.kind === "pgn") {
    lines.load(key, { start: detected.start, moves: detected.moves.map((m) => m.uci), title: detected.title }, { undo: tr("Paste game") })
  } else {
    const fen = detected.kind === "fen" ? detected.fen : detected.fens[0]
    if (detected.kind === "fen" && !detected.check.ok) {
      lines.load(key, { start: fen }, { undo: tr("Paste position") })
      status(tr("Not a legal position: shown as a diagram. S opens the board editor to fix it."), { timeout: 6000 })
      return
    }
    lines.load(key, { start: fen }, { undo: tr("Paste position") })
  }
  focusedBoard()?.refresh()
})

// A new position to analyse: the pasted game's moves become its main line.
handle("paste.analyse", async () => {
  if (!detected) return false
  if (detected.kind === "pgn") {
    return analyseNew({ start: detected.start, moves: detected.moves.map((m) => m.uci), title: detected.title, origin: "paste" })
  }
  const fen = detected.kind === "fen" ? detected.fen : detected.fens[0]
  if (detected.kind === "fen" && !detected.check.ok) {
    return status(tr("Not a legal position: show it on a board (b) and fix it in the board editor first"), { kind: "error" }) || false
  }
  return analyseNew({ start: fen, origin: "paste" })
})

handle("paste.collect", () => (detected ? collectPaste(detected) : false))
handle("paste.import", () => (detected?.kind === "pgn" ? openImport(pasted) : false))
handle("library.import", () => chooseFile())

// ⌘V outside text fields. In a field, pasting types as usual.
document.addEventListener("paste", (e) => {
  const target = e.target
  if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA)$/.test(target.tagName))) return
  const text = e.clipboardData?.getData("text/plain")
  if (!text) return
  e.preventDefault()
  detect(text)
})
