// Boot: read the registry the server put into the page, start the keys, take over the workspace.

import { handle, setRegistry, setTeachKeys } from "./core/commands.js"
import { ctx, emit, on, setLayer, status } from "./core/context.js"
import { cancelPending, initKeys, keyPerf } from "./core/keys.js"
import { initWorkspace, restoreToggles } from "./core/layout.js"
import { escapeSelection } from "./core/lists.js"
import "./core/cmdline.js"
import "./core/help.js"
import "./core/hints.js"
import "./core/islands.js"
import "./core/scroll.js"
import { detect } from "./core/paste.js"
import { loadJournal } from "./core/analysis.js"
import { announce } from "./core/charts.js"
import { importCsm, importSettings } from "./core/settings.js"

const boot = JSON.parse(document.getElementById("boot").textContent)
// Modules may have added to window.SPOS while they loaded (imports run first): add, don't replace.
Object.assign((window.SPOS ||= {}), {
  views: boot.views, modes: boot.modes, themes: boot.themes, tokens: boot.tokens, settings: boot.settings,
  settingsSchema: boot.settingsSchema, keyPerf, ctx,
})

/** Settings that the page applies itself (spec 07 §5); modules read window.SPOS.settings and listen to "settings". */
function applySettings(values) {
  window.SPOS.settings = values
  document.documentElement.dataset.keycaps = values["keys.keycaps"]
  document.documentElement.dataset.letters = values["board.letters"]
  setTeachKeys(values["keys.teach"] !== false)
  emit("settings", values)
}

setRegistry(boot.registry)
ctx.mode = boot.mode
ctx.theme = boot.theme
ctx.launched = boot.launched
applySettings(boot.settings)

handle("layer.escape", () => {
  cancelPending()
  const active = document.activeElement
  if (active && active !== document.body && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) {
    active.blur()
    setLayer("normal")
    return
  }
  if (escapeSelection()) return
  if (window.SPOS.trainEscape?.()) return
  setLayer("normal")
  status("", { timeout: 1 })
})

handle("form.submit", () => {
  const form = document.activeElement?.closest("form") || ctx.pane?.el?.querySelector("form")
  if (!form) return false
  if (form.hasAttribute("data-paste-form")) {
    const field = form.querySelector("textarea")
    document.activeElement?.blur()
    setLayer("normal")
    detect(field.value)
    return
  }
  if (form.hasAttribute("data-csm-import")) {
    const field = form.querySelector("input")
    document.activeElement?.blur()
    setLayer("normal")
    importCsm(field.value)
    return
  }
  if (form.hasAttribute("data-settings-import")) {
    const field = form.querySelector("textarea")
    document.activeElement?.blur()
    setLayer("normal")
    importSettings(field.value)
    return
  }
  if (form.hasAttribute("data-comment-form")) {
    document.activeElement?.blur() // leaving the field saves the comment (core/analysis.js)
    setLayer("normal")
    return
  }
  if (form.hasAttribute("data-notes")) {
    document.activeElement?.blur()
    setLayer("normal")
    status("Note submitted (demo: notes are not stored in phase 0)", { kind: "good" })
    return
  }
  form.requestSubmit()
})

on("effects", (effects) => {
  if (effects.settings) applySettings(effects.settings)
  if (effects.registry) setRegistry(effects.registry) // :map, :unmap: the keys work at once
  if (effects.themes) window.SPOS.themes.themes = effects.themes
  if (effects.copy) navigator.clipboard?.writeText(effects.copy).catch(() => status("The browser didn't allow copying", { kind: "error" }))
  if (effects.theme) {
    document.getElementById("theme").textContent = effects.theme.css
    ctx.theme = effects.theme.name
    window.SPOS.tokens = effects.theme.tokens
    document.documentElement.dataset.pieces = effects.theme.tokens["piece-set"] || "cburnett"
    document.documentElement.toggleAttribute("data-figurines", effects.theme.tokens.figurines === true)
    document.documentElement.dataset.coords = effects.theme.tokens["board-coords"] || "inside"
    for (const img of document.querySelectorAll("img.miniboard")) {
      const url = new URL(img.src)
      url.searchParams.set("t", effects.theme.boardHash)
      img.src = url.pathname + url.search
    }
    emit("theme", effects.theme)
  }
  if (effects.quit) {
    setTimeout(() => {
      document.getElementById("workspaces").replaceChildren(
        Object.assign(document.createElement("div"), {
          className: "empty",
          textContent: "Spaced Positions has stopped. Start it again from its icon or with spos.",
        }),
      )
    }, 600)
  }
})

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => { ctx.prefersDark = e.matches })

restoreToggles()
initKeys()
initWorkspace(document.querySelector(".workspace"))
loadJournal() // undo reaches analysis changes made before a reload (spec 09 §5)
setTimeout(announce, 1500) // records and milestones reached and not announced yet
history.replaceState({ mode: ctx.mode }, "", location.pathname + location.search)
