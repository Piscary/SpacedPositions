// The key intro on Home (templates/views/today.html, "Getting around"): seven keys to try, each ticked off the first
// time it is used by key (a click doesn't count: the point is the key). Progress is kept in this browser.

import { on, status } from "./context.js"
import { tr } from "./i18n.js"

const KEY = "spos.intro"

function done() {
  try { return new Set(JSON.parse(localStorage.getItem(KEY) || "[]")) } catch { return new Set() }
}

function save(steps) {
  try { localStorage.setItem(KEY, JSON.stringify([...steps])) } catch { /* not kept: it starts again next time */ }
}

function paint() {
  const steps = done()
  for (const box of document.querySelectorAll("[data-intro]")) {
    const items = [...box.querySelectorAll("[data-step]")]
    items.forEach((li) => li.classList.toggle("is-done", steps.has(li.dataset.step)))
    const n = items.filter((li) => steps.has(li.dataset.step)).length
    box.querySelector("[data-intro-count]").textContent = tr("{n} of {total}", { n, total: items.length })
    box.querySelector("[data-intro-done]").hidden = n < items.length
  }
}

on("command", ({ id, source }) => {
  if (source !== "key") return
  const item = [...document.querySelectorAll("[data-intro] [data-step]")].find((li) => li.dataset.commands.split(" ").includes(id))
  if (!item) return
  const steps = done()
  if (steps.has(item.dataset.step)) return
  steps.add(item.dataset.step)
  save(steps)
  paint()
  const total = item.closest("[data-intro]").querySelectorAll("[data-step]").length
  status(steps.size >= total ? tr("All seven: you know your way around") : tr("Tick: {n} of {total} keys tried", { n: steps.size, total }), { kind: "good", timeout: 2500 })
})
on("pane:load", paint)
on("layout", paint)
on("workspace", paint)
