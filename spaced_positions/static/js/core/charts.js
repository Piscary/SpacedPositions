// Charts are SVG from the server (stats/charts.py); this island makes them keyboard-inspectable (spec 05 · G):
// j/k move between the charts of the Stats pane, h/l move a cursor over the focused chart's points (the read-out
// row shows the value), ↵ drills down, t shows the table, 1–5 switch the period. Numbers and tiles with data-drill
// drill down on click too.

import { handle } from "./commands.js"
import { ctx, status } from "./context.js"
import { switchMode } from "./layout.js"

const cursors = new WeakMap() // figure → index

const figures = (root) => [...root.querySelectorAll("figure[data-chart]")]
const statsRoot = () => ctx.pane?.el?.querySelector("[data-island='stats']") || null
const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function pointsOf(figure) {
  try {
    return JSON.parse(figure.dataset.points || "[]")
  } catch {
    return []
  }
}

function focusChart(figure) {
  const root = figure.closest("[data-island='stats']")
  for (const f of figures(root)) f.classList.toggle("is-focused", f === figure)
  figure.scrollIntoView({ block: "nearest" })
  if (!cursors.has(figure)) setCursor(figure, pointsOf(figure).length - 1)
}

function focused(root) {
  return root.querySelector("figure[data-chart].is-focused") || figures(root)[0] || null
}

function setCursor(figure, index) {
  const points = pointsOf(figure)
  if (!points.length) return
  const i = Math.max(0, Math.min(points.length - 1, index))
  cursors.set(figure, i)
  for (const el of figure.querySelectorAll("[data-i]")) el.classList.toggle("is-cursor", Number(el.dataset.i) === i)
  figure.querySelector("[data-readout]").textContent = points[i].text + (points[i].drill ? "  ·  ↵" : "")
}

/** A drill-down: a Library query ("motif:gabel", "games:", "puzzles:state:mature") or a Streak ("train:#fork"). */
export async function drill(target) {
  if (target === undefined || target === null) return false
  if (target.startsWith("train:")) {
    return window.SPOS.train.start({ mode: "streak", lives: 0, look: "normal", side: "move", filter: target.slice(6) })
  }
  if (target.startsWith("tag:")) return drill(`${target.slice(4)}:`) // a family: its tags in the Library
  const m = /^(games|puzzles|players|sources|tags):(.*)$/.exec(target)
  if (ctx.mode !== "library") await switchMode("library")
  return window.SPOS.library.setQuery(m ? m[2] : target, m ? m[1] : "positions")
}

export function mountStats(el) {
  load(el, el.dataset.period || "")
}

async function load(el, period) {
  const html = await fetch(`/stats/sections/${period ? `?period=${period}` : ""}`).then((r) => r.text()).catch(() => null)
  if (html === null) return status("Stats: the app is not reachable", { kind: "error" })
  el.innerHTML = html
  window.htmx?.process(el)
  for (const figure of figures(el)) {
    const points = pointsOf(figure)
    if (points.length) setCursor(figure, points.length - 1)
  }
}

// Mouse: hovering a point moves the cursor, clicking drills down.
document.addEventListener("pointerover", (e) => {
  const point = e.target.closest?.("figure[data-chart] [data-i]")
  if (point) setCursor(point.closest("figure[data-chart]"), Number(point.dataset.i))
})
document.addEventListener("click", (e) => {
  const tile = e.target.closest?.("[data-drill]")
  if (tile && tile.dataset.drill !== undefined && tile.closest("[data-island='stats'], [data-island='home']")) return drill(tile.dataset.drill)
  const point = e.target.closest?.("figure[data-chart] [data-i]")
  if (!point) return
  const figure = point.closest("figure[data-chart]")
  focusChart(figure)
  const p = pointsOf(figure)[Number(point.dataset.i)]
  if (p?.drill) drill(p.drill)
})

const withChart = (fn) => (args) => {
  const root = statsRoot()
  const figure = root && focused(root)
  if (!figure) return false
  return fn(figure, root, args)
}

handle("chart.next", withChart((figure, root, [step]) => {
  const all = figures(root).filter((f) => !f.closest("[data-section].is-collapsed"))
  const i = all.indexOf(figure)
  const next = all[Math.max(0, Math.min(all.length - 1, i + (step === "prev" ? -1 : 1)))]
  if (!next || next === figure && i !== -1) return false
  focusChart(next)
}))
handle("chart.cursor", withChart((figure, root, [step]) => {
  if (!figure.classList.contains("is-focused")) focusChart(figure)
  const i = cursors.get(figure) ?? pointsOf(figure).length - 1
  const n = pointsOf(figure).length
  const target = { prev: i - 1, next: i + 1, first: 0, last: n - 1 }[step]
  setCursor(figure, target)
}))
handle("chart.drill", withChart((figure) => {
  const p = pointsOf(figure)[cursors.get(figure) ?? -1]
  if (!p?.drill) return status("Nothing to drill into here", { timeout: 1500 }) || false
  return drill(p.drill)
}))
handle("chart.table", withChart((figure) => {
  const table = figure.querySelector(".chart__table")
  if (!table) return false
  table.hidden = !table.hidden
  figure.classList.toggle("is-table", !table.hidden)
}))
handle("stats.period", async ([period]) => {
  const root = statsRoot() || document.querySelector("#ws-stats [data-island='stats']")
  if (!root) return false
  root.dataset.period = period
  await load(root, period)
  fetch("/state/stats/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ subject: { period } }),
  }).catch(() => {})
  status(`Period: ${period}`, { timeout: 1500 })
})

// ── Home ──────────────────────────────────────────────────────────────────────────────────────────────────────

handle("home.analysis", () => {
  const el = document.querySelector("[data-continue-analysis]")
  if (!el) return status("No analysis to continue: :analyse opens one", { kind: "error" }) || false
  return window.SPOS.analysis.open(el.dataset.continueAnalysis, { node: Number(el.dataset.node) || null })
})
handle("home.collect", () => switchMode("collect"))
handle("home.dismiss", async () => {
  const banner = document.querySelector("[data-banner]")
  if (!banner) return false
  banner.remove()
  await fetch("/stats/seen/", { method: "POST", headers: { "X-CSRFToken": csrf() } }).catch(() => {})
})

/** Achievements not announced yet: once in the status line (spec 05 · AchievementChip). */
export async function announce() {
  const data = await fetch("/stats/seen/", { method: "POST", headers: { "X-CSRFToken": csrf() } }).then((r) => r.json()).catch(() => null)
  const labels = (data?.achievements || []).map((a) => a.label)
  if (labels.length) status(labels.join(" · "), { kind: "good", timeout: 8000 })
}
