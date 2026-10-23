// Key event → key token as written in the keymap (mirrors design/lib.py parse_key). Pure: no DOM, so it is
// unit-tested with node (tests/js).

const NAMED = {
  " ": "space", Enter: "enter", Escape: "esc", Tab: "tab", Backspace: "backspace", Delete: "delete",
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Home: "home", End: "end",
  PageUp: "pageup", PageDown: "pagedown",
}
const MOD_ORDER = ["mod", "ctrl", "alt", "shift"]

/**
 * Printable keys match on the produced character (so `?` and `:` work on any layout); Alt chords match on the
 * physical key, because macOS turns ⌥k into "˚" (spec 02 §4). Returns null for a modifier on its own.
 */
export function tokenFromEvent(e, mac) {
  if (e.isComposing || e.key === "Dead" || e.key === "Unidentified" || !e.key) return null
  const mods = new Set()
  if (mac ? e.metaKey : e.ctrlKey) mods.add("mod")
  if (mac && e.ctrlKey) mods.add("ctrl")
  if (e.altKey) mods.add("alt")
  let key
  if (e.altKey && /^(Key[A-Z]|Digit\d)$/.test(e.code || "")) key = e.code.slice(-1).toLowerCase()
  else if (NAMED[e.key]) key = NAMED[e.key]
  else if (/^F\d{1,2}$/.test(e.key)) key = e.key.toLowerCase()
  else if (e.key.length === 1) key = e.key
  else return null
  if (key.length === 1) {
    if (mods.size) {
      key = key.toLowerCase()
      if (e.shiftKey) mods.add("shift")
    }
  } else if (e.shiftKey) mods.add("shift")
  return [...MOD_ORDER.filter((m) => mods.has(m)), key].join("+")
}
