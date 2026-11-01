// Coaching (spec 17): the Lessons and Lesson panes, `L` (to a lesson), the homework file; on the student's side the
// homework session and the results file; results files dropped on the coach's app.

import { handle, run } from "./commands.js"
import { ctx, emit, newest, on, saveFile, status } from "./context.js"
import { nodeOf } from "./layout.js"
import { openCmdline } from "./cmdline.js"
import { resetList, targetRows } from "./lists.js"
import { tr } from "./i18n.js"

const loads = newest()
const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const islands = (kind) => [...document.querySelectorAll(`[data-island='${kind}']`)]

async function load(el, url) {
  const current = loads(el)
  const keep = el.querySelector("[data-row].is-cursor")?.dataset.row
  const html = await fetch(url).then((r) => (r.ok ? r.text() : null)).catch(() => null)
  if (html === null || !current()) return
  el.innerHTML = html
  window.htmx?.process(el)
  const list = el.querySelector("[data-list]")
  if (list) resetList(list, { index: Math.max(0, [...list.querySelectorAll("[data-row]")].findIndex((r) => r.dataset.row === keep)) })
}

const showLessons = (el) => load(el, "/coach/lessons/")
function showLesson(el, pk) {
  if (!pk) return
  el.dataset.lesson = pk
  load(el, `/coach/lessons/${pk}/`)
}
export const mountLessons = showLessons
export function mountLesson(el) {
  if (el.dataset.lesson) showLesson(el, el.dataset.lesson)
}

// The Lessons pane's cursor shows its lesson in the Lesson pane of the same link group.
on("cursor", ({ group, id }) => {
  if (!/^L\d+$/.test(id || "")) return
  for (const el of islands("lesson")) {
    if (el.closest(".workspace").dataset.mode === ctx.mode && nodeOf(el.closest("[data-pane]"))?.group === group) showLesson(el, id.slice(1))
  }
})
on("effects", (effects) => {
  if (!("lessons" in effects)) return // 0: a lesson was deleted
  islands("lessons").forEach(showLessons)
  islands("lesson").forEach((el) => showLesson(el, el.dataset.lesson || effects.lessons))
})

/** What `L` adds: the Library's selection (or the row under the cursor), else the open analysis. */
function selection() {
  const list = ctx.pane?.el?.querySelector("[data-list]")
  const ids = list ? targetRows(list).ids.filter((id) => /^[pg]\d+$/.test(id)) : []
  if (ids.length) return ids
  const t = window.SPOS.analysis?.current?.()
  return t ? [t.position.id] : []
}

handle("lesson.add", ([name] = [], { source } = {}) => {
  if (!name) return openCmdline("lesson-add ") // which lesson: a title nobody has makes a new one
  const refs = selection()
  if (!refs.length) return status(tr("Select positions or games in the Library, or open one in Analyse"), { kind: "error" }) || false
  return run("lesson.addto", [name, ...refs], { source })
})

// `a` in a Lesson pane: any position of the Library, found by typing (title, source, motif:…, p529), joins this lesson
handle("lesson.find", ([position] = [], { source } = {}) => {
  const lesson = ctx.pane?.el?.querySelector("[data-lesson-list]")?.dataset.lesson
  if (!lesson) return status(tr("Open a lesson first: the Lessons pane, ↵ or a click"), { kind: "error" }) || false
  if (!position) return openCmdline("lesson-find ")
  return run("lesson.addto", [`L${lesson}`, position], { source })
})

function lessonRow() {
  const list = ctx.pane?.el?.querySelector("[data-lesson-list]")
  return list?.querySelector("[data-row].is-cursor") || null
}
handle("lesson.removeitem", () => {
  const row = lessonRow()
  return row ? run("lesson.remove", [row.dataset.item]) : false
})
handle("lesson.noteitem", () => {
  const row = lessonRow()
  if (!row) return false
  openCmdline(`lesson-note ${row.dataset.item} ${row.querySelector(".lesson__note")?.textContent || ""}`)
})

/** The lesson the keys are on: the Lesson pane's, or the row under the Lessons pane's cursor. */
function currentLesson() {
  const el = ctx.pane?.el
  return el?.querySelector("[data-lesson-list]")?.dataset.lesson || el?.querySelector("[data-lessons-list] [data-row].is-cursor")?.dataset.lesson || null
}

handle("lesson.homework", async (args, { source } = {}) => {
  const lesson = currentLesson()
  if (!lesson) return status(tr("Choose a lesson in the Lessons pane first"), { kind: "error" }) || false
  if (!args.length && source !== "cmdline") return openCmdline("homework ") // the instructions (and due=2026-11-14), or nothing
  const words = args.join(" ").split(/\s+/)
  const due = words.find((w) => /^due=\d{4}-\d{2}-\d{2}$/.test(w))?.slice(4) || ""
  const text = words.filter((w) => !w.startsWith("due=")).join(" ")
  const name = await saveFile(`/coach/lessons/${lesson}/homework/?${new URLSearchParams({ text, due })}`)
  if (name) status(tr("{file} written: send it to your students; their results files come back here (drop them on this window)", { file: name }), { kind: "good", timeout: 8000 })
})

const firstHomework = () => document.querySelector("[data-homework]")?.dataset.homework || null

handle("homework.start", async ([id] = []) => {
  id ||= firstHomework()
  if (!id) return status(tr("No homework: it comes as a pack from your coach"), { timeout: 3000 }) || false
  const data = await fetch(`/coach/homework/${id}/cards/`).then((r) => r.json()).catch(() => null)
  if (!data?.cards?.length) return status(tr("The homework's puzzles are not here: import the pack again"), { kind: "error" }) || false
  return window.SPOS.train.start({ mode: "review", cards: data.cards, look: "normal", side: "move" })
})

handle("homework.send", async ([id] = []) => {
  id ||= firstHomework()
  if (!id) return false
  const name = await saveFile(`/coach/homework/${id}/results/`)
  if (name) status(tr("{file} written: look at it, then send it to your coach (it holds only this homework's results)", { file: name }), { kind: "good", timeout: 8000 })
})

/** A results file dropped on the coach's app (core/packs.js passes it here). */
export async function importResults(file) {
  const response = await fetch("/coach/results/", { method: "POST", headers: { "X-CSRFToken": csrf() }, body: await file.text() }).catch(() => null)
  const data = await response?.json().catch(() => null)
  status(data?.message || tr("Could not read the results"), { kind: data?.ok ? "good" : "error", timeout: 6000 })
  if (data?.ok) emit("effects", { lessons: data.lesson || true })
}
