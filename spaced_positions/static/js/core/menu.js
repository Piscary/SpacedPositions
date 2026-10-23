// Menu (spec 05 · C): the view picker, context menus, lists of buffers. Keyboard: j/k or ↑↓, Enter, each item's
// own key, Esc. Resolves with the chosen item's value, or null.

import { ctx, keycaps, setLayer } from "./context.js"
import { setOverlayHandler } from "./keys.js"

let open = null

export function openMenu({ title, items, anchor = null }) {
  close(null)
  return new Promise((resolve) => {
    const el = document.createElement("div")
    el.className = "menu"
    el.setAttribute("role", "menu")
    if (title) {
      const head = document.createElement("div")
      head.className = "menu__title"
      head.textContent = title
      el.append(head)
    }
    const rows = []
    for (const item of items) {
      if (item.separator) {
        el.append(Object.assign(document.createElement("div"), { className: "menu__sep" }))
        continue
      }
      const row = document.createElement("div")
      row.className = `menu__item${item.disabled ? " is-disabled" : ""}`
      row.setAttribute("role", "menuitem")
      const label = document.createElement("span")
      label.className = "menu__label"
      label.textContent = item.label
      row.append(label)
      if (item.note) {
        const note = document.createElement("span")
        note.className = "menu__note"
        note.textContent = item.note
        row.append(note)
      }
      if (item.keys) row.append(keycaps(item.keys))
      row.addEventListener("click", () => choose(rows.indexOf(row)))
      row.addEventListener("pointermove", () => setCursor(rows.indexOf(row)))
      rows.push(row)
      el.append(row)
    }
    document.body.append(el)
    position(el, anchor)

    let cursor = 0
    const setCursor = (i) => {
      cursor = (i + rows.length) % rows.length
      rows.forEach((r, j) => r.classList.toggle("is-cursor", j === cursor))
      rows[cursor]?.scrollIntoView({ block: "nearest" })
    }
    const choose = (i) => {
      const item = items.filter((x) => !x.separator)[i]
      if (!item || item.disabled) return
      close(item.value)
    }
    const previousLayer = ctx.layer
    open = { el, resolve, previousLayer }
    ctx.overlay = "menu"
    setCursor(0)
    setOverlayHandler((e, token) => {
      if (token === "esc") return close(null)
      if (token === "j" || token === "down") return setCursor(cursor + 1)
      if (token === "k" || token === "up") return setCursor(cursor - 1)
      if (token === "enter") return choose(cursor)
      const index = items.filter((x) => !x.separator).findIndex((x) => x.key === token)
      if (index >= 0) return choose(index)
    })
    setTimeout(() => document.addEventListener("pointerdown", outside, true))
  })
}

function outside(e) {
  if (open && !open.el.contains(e.target)) close(null)
}

function close(value) {
  if (!open) return
  const { el, resolve, previousLayer } = open
  open = null
  el.remove()
  ctx.overlay = null
  setOverlayHandler(null)
  document.removeEventListener("pointerdown", outside, true)
  setLayer(previousLayer === "pending" ? "normal" : previousLayer)
  resolve(value)
}

function position(el, anchor) {
  const box = el.getBoundingClientRect()
  let x, y
  if (anchor instanceof Element) {
    const r = anchor.getBoundingClientRect()
    x = r.left + 8
    y = r.top + 28
  } else if (anchor && "x" in anchor) {
    x = anchor.x
    y = anchor.y
  } else {
    x = (innerWidth - box.width) / 2
    y = innerHeight / 3 - box.height / 3
  }
  el.style.left = `${Math.max(4, Math.min(x, innerWidth - box.width - 4))}px`
  el.style.top = `${Math.max(4, Math.min(y, innerHeight - box.height - 4))}px`
}
