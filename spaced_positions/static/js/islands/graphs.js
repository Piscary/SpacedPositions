// The eval graph and the variation graph (spec 05 · F): drawn here from the tree the browser already has, so the
// cursor moves with the board and a click goes to the move. Eval graph: white's advantage over the main line, clipped
// at ±5, mistakes marked (? and ?? and drops of 1.5 or more). Variation graph: the main line across, variations
// below the move they branch from, dots coloured by mark.

import { on } from "../core/context.js"
import { nodeOf } from "../core/layout.js"
import { kidsOf, mainlineOf, moveTo, path, treeOf } from "../core/analysis.js"
import { tr, trn } from "../core/i18n.js"

const NS = "http://www.w3.org/2000/svg"
const CLIP = 500

const el = (name, attrs = {}) => {
  const node = document.createElementNS(NS, name)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  return node
}

function keyOf(island) {
  const pane = island.closest("[data-pane]")
  const node = nodeOf(pane)
  const mode = pane.closest(".workspace").dataset.mode
  return `${mode}:${node?.group && !node.pinned ? node.group : node?.id}`
}

const islands = () => [...document.querySelectorAll("[data-island='evalgraph'], [data-island='vargraph']")]

function value(n) {
  if (!n?.eval) return null
  if (n.eval.mate !== null && n.eval.mate !== undefined) return n.eval.mate > 0 || (n.eval.mate === 0 && n.eval.cp > 0) ? CLIP : -CLIP
  return Math.max(-CLIP, Math.min(CLIP, n.eval.cp))
}

function evalText(n) {
  if (!n?.eval) return tr("not evaluated")
  if (n.eval.mate !== null && n.eval.mate !== undefined) return n.eval.mate === 0 ? "#" : `${n.eval.mate > 0 ? "+" : "−"}M${Math.abs(n.eval.mate)}`
  return `${n.eval.cp > 0 ? "+" : n.eval.cp < 0 ? "−" : ""}${Math.abs(n.eval.cp / 100).toFixed(2)}`
}

function drawEval(island) {
  const t = treeOf(keyOf(island))
  const box = island.querySelector("[data-graph]")
  const readout = island.querySelector("[data-readout]")
  if (!t) {
    box.replaceChildren()
    readout.textContent = tr("Open a game or a position in this link group.")
    return
  }
  const line = mainlineOf(t)
  const W = 600
  const H = 120
  const step = W / Math.max(1, line.length - 1)
  const y = (v) => H / 2 - (v / CLIP) * (H / 2 - 4)
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", class: "evalgraph__svg" })
  svg.append(el("line", { x1: 0, y1: H / 2, x2: W, y2: H / 2, class: "chart__base" }))
  const known = line.map((n, i) => [i, value(n)]).filter(([, v]) => v !== null)
  if (known.length > 1) {
    const top = known.map(([i, v]) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
    svg.append(el("polygon", { points: `0,${H / 2} ${top} ${(known.at(-1)[0] * step).toFixed(1)},${H / 2}`, class: "evalgraph__area" }))
    svg.append(el("polyline", { points: top, class: "chart__line s-chart-1" }))
  }
  // the cursor: the move itself on the main line, else the last main-line move on its path (a variation's branch point)
  const onPath = new Set(path(t, t.cursor).map((n) => n.id))
  const at = line.reduce((best, n, i) => (onPath.has(n.id) ? i : best), 0)
  const whiteStarts = line[0].fen.split(" ")[1] === "w"
  line.forEach((n, i) => {
    const v = value(n)
    const prev = i ? value(line[i - 1]) : null
    const white = whiteStarts === (i % 2 === 1) // the move into ply i was white's
    const drop = v !== null && prev !== null ? (white ? prev - v : v - prev) : 0
    const mistake = (n.nags || []).some((x) => x === 2 || x === 4) || drop >= 150
    svg.append(el("rect", { x: (i * step - step / 2).toFixed(1), y: 0, width: Math.max(step, 1).toFixed(1), height: H, class: "evalgraph__hit", "data-node": n.id }))
    if (mistake && i) svg.append(el("circle", { cx: (i * step).toFixed(1), cy: y(v ?? 0).toFixed(1), r: 3, class: "evalgraph__mistake" }))
    if (i === at) {
      svg.append(el("line", { x1: (i * step).toFixed(1), y1: 0, x2: (i * step).toFixed(1), y2: H, class: "evalgraph__cursor" }))
      readout.textContent = `${i ? `${Math.ceil(i / 2)}${white ? "." : "…"}${n.san}` : tr("Start")} · ${evalText(n)}`
    }
  })
  if (!known.length) readout.textContent = tr("No evaluations yet: :evaluate runs the engine over the main line.")
  box.replaceChildren(svg)
}

function drawVariations(island) {
  const t = treeOf(keyOf(island))
  const box = island.querySelector("[data-graph]")
  if (!t) {
    box.replaceChildren()
    island.querySelector("[data-readout]").textContent = tr("Open a game or a position in this link group.")
    return
  }
  // layout: depth-first, the main child continues the row, other children open new rows below
  const pos = new Map()
  let rows = 0
  const place = (id, x, row) => {
    pos.set(id, [x, row])
    const kids = kidsOf(t, id)
    kids.forEach((k, i) => {
      if (i === 0) place(k.id, x + 1, row)
      else place(k.id, x + 1, ++rows)
    })
  }
  place(t.root, 0, 0)
  const maxX = Math.max(...[...pos.values()].map(([x]) => x), 1)
  const DX = 16
  const DY = 14
  const W = (maxX + 1) * DX + 8
  const H = (rows + 1) * DY + 8
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "vargraph__svg", width: W, height: H })
  const onPath = new Set(path(t, t.cursor).map((n) => n.id))
  for (const [id, [x, row]] of pos) {
    const n = t.nodes.get(id)
    if (n.parent !== null) {
      const [px, prow] = pos.get(n.parent)
      svg.append(el("path", { d: `M${px * DX + 6},${prow * DY + 6} L${px * DX + 6},${row * DY + 6} L${x * DX + 6},${row * DY + 6}`,
                              class: `vargraph__edge${onPath.has(id) ? " is-path" : ""}` }))
    }
  }
  for (const [id, [x, row]] of pos) {
    const n = t.nodes.get(id)
    svg.append(el("circle", { cx: x * DX + 6, cy: row * DY + 6, r: id === t.cursor ? 5 : 3.5, "data-node": id,
                              class: `vargraph__dot${n.mark ? ` is-${n.mark}` : ""}${id === t.cursor ? " is-cursor" : ""}${onPath.has(id) ? " is-path" : ""}` }))
  }
  box.replaceChildren(svg)
  box.querySelector(".is-cursor")?.scrollIntoView({ block: "nearest", inline: "nearest" })
  const n = t.nodes.get(t.cursor)
  island.querySelector("[data-readout]").textContent = `${trn("{n} move", "{n} moves", pos.size - 1)} · ${trn("{n} line", "{n} lines", rows + 1)}${n?.san ? ` · ${tr("at {move}", { move: n.san })}` : ""}`
}

function draw(island) {
  if (island.dataset.island === "evalgraph") drawEval(island)
  else drawVariations(island)
}

export function mountGraph(island) {
  draw(island)
  island.addEventListener("click", (e) => {
    const target = e.target.closest("[data-node]")
    if (target) moveTo(keyOf(island), Number(target.dataset.node))
  })
}

for (const type of ["analysis:cursor", "analysis:tree"]) {
  on(type, ({ key }) => {
    for (const island of islands()) if (keyOf(island) === key) draw(island)
  })
}
on("layout", () => islands().forEach(draw))
