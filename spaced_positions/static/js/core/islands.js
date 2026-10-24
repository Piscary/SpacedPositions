// Islands (spec 09 §3): small JS components attached to server-rendered markup by `data-island`. Mounted when a
// workspace renders and when a pane fragment arrives.

import { on } from "./context.js"
import { mountBoard, renderLineText } from "../islands/board.js"
import { mountTrain } from "../islands/train.js"
import { mountInspector, mountMoves } from "./analysis.js"
import { mountEngine } from "./engine.js"
import { mountFilters, mountLibrary } from "./library.js"
import { mountEntry } from "./collect.js"

const MOUNT = {
  board: mountBoard,
  "line-text": renderLineText,
  train: mountTrain,
  moves: mountMoves,
  inspector: mountInspector,
  engine: mountEngine,
  library: mountLibrary,
  filters: mountFilters,
  entry: mountEntry,
}

export function mountIslands(root = document) {
  for (const el of root.querySelectorAll("[data-island]")) {
    if (el.dataset.mounted) continue
    el.dataset.mounted = "1"
    MOUNT[el.dataset.island]?.(el)
  }
}

on("layout", ({ el }) => mountIslands(el))
on("pane:load", ({ el }) => mountIslands(el))
