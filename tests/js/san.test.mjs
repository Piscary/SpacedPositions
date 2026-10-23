// node --experimental-default-type=module --test tests/js
import assert from "node:assert/strict"
import { test } from "node:test"

import { matchMoves } from "../../spaced_positions/static/js/core/san.js"
import { Chess } from "../../spaced_positions/static/vendor/chess.js"

const moves = (fen) => new Chess(fen).moves({ verbose: true })
const sans = (r) => r.candidates.map((m) => m.san)
const START = new Chess().fen()

test("SAN prefixes narrow the candidates", () => {
  assert.deepEqual(sans(matchMoves("e", moves(START))), ["e3", "e4"])
  assert.equal(matchMoves("e4", moves(START)).exact.san, "e4")
  assert.deepEqual(sans(matchMoves("N", moves(START))), ["Na3", "Nc3", "Nf3", "Nh3"])
  assert.equal(matchMoves("Nf", moves(START)).exact.san, "Nf3")
})

test("German letters, lower-case pieces and UCI", () => {
  assert.equal(matchMoves("Sf3", moves(START)).exact.san, "Nf3")
  assert.equal(matchMoves("sf3", moves(START)).exact.san, "Nf3")
  assert.equal(matchMoves("nf3", moves(START)).exact.san, "Nf3")
  assert.equal(matchMoves("g1f3", moves(START)).exact.san, "Nf3")
})

test("promotions with and without =, German too", () => {
  const promo = moves("8/1P6/8/8/8/8/8/k1K5 w - - 0 1")
  assert.equal(matchMoves("b8", promo).candidates.length, 4)
  assert.equal(matchMoves("b8Q", promo).exact.san, "b8=Q")
  assert.equal(matchMoves("b8=D", promo).exact.san, "b8=Q")
  assert.equal(matchMoves("b7b8n", promo).exact.san, "b8=N")
})

test("castling with zeros or letters", () => {
  const both = moves("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
  assert.equal(matchMoves("0-0", both).exact.san, "O-O")
  assert.equal(matchMoves("O-O-O", both).exact.san, "O-O-O")
  assert.equal(matchMoves("o-o", both).exact.san, "O-O")
})

test("b is the b-file first, then the bishop", () => {
  const m = moves("4k3/8/8/8/8/8/1P6/4KB2 w - - 0 1")
  assert.deepEqual(sans(matchMoves("b", m)), ["b3", "b4"])
  assert.equal(matchMoves("be2", m).exact.san, "Be2")
  assert.deepEqual(sans(matchMoves("Q", m)), [])
})
