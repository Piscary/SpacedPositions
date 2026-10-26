# 13 · Pack licensing, the marketplace and the way there (plan)

Status: **plan**. Nothing here is built, and the marketplace is not part of the test version. What has to be decided
early is the **pack format**: packs made today should keep working when licences and a marketplace arrive. §2 is that
format; the rest is the plan and the milestones (§6) that decide when each step starts.

## 1 · Goals, and an honest limit

- **Authors** (people you know first, later coaches) put their collections into packs; you review and publish them;
  people buy them, or your course students get them as part of the course.
- A licensed pack can be **imported and trained, not exported**: no pack export, no PGN export, no bulk copying of
  its positions, and the app shows whose work it is.
- People should still own their training: their attempts, notes and their own analysis are theirs.

**The limit:** Spaced Positions is free software under the GPL-3.0. Anyone may change it and run the changed
version, and GPL-3.0 §3 states that the program is not an "effective technological measure": removing a restriction
from the app is allowed under copyright law. So the app can make taking content **hard and obvious, never
impossible**. What protects authors is, in this order:

1. the **licence contract** the buyer agrees to (the content is not GPL; only the app is),
2. **traceability**: every sold copy is personal and signed, so a leaked file says whose copy it was,
3. the **official app** honouring the licence (no export, a visible author line), which is what nearly everyone uses,
4. the **value of the source**: updates, corrections and new volumes reach paying owners only.

This is how e-book and music shops without hard DRM work, and it is fair to say so to authors up front.

## 2 · The licence in the pack format (format 2)

Today a manifest has a licence *text*, an optional `for` (personal copy) and a `copy` id; personal copies are already
left out of exports. Format 2 adds a structured licence and a signature. Format 1 packs keep working unchanged
(treated as `kind: "open"` with their text).

```json
"licence": {
  "kind": "commercial",                 // open · personal · course · commercial
  "holder": "Jane Author, Example Press",
  "title": "Personal licence",
  "text": "…",                          // shown in the import preview, kept with the pack
  "terms": "https://example.org/terms/pack-123",
  "rights": {
    "export": false,                    // pack export, PGN export, bulk copy of FENs
    "print": false,                     // printing / PDF of its positions (when publishing exists)
    "share_analysis": true,             // the licensee's own analysis may be exported (without the positions' texts)
    "derivatives": "private"            // none · private (own packs, not shared) · allowed
  },
  "licensee": { "name": "Ben Muster", "id": "order-2027-000123" },
  "issued": "2027-03-01"
},
"signature": { "issuer": "spaced-positions-shop-2027", "alg": "ed25519", "value": "…" }
```

- **Signature**: over the manifest and a hash of every file in the pack. The app ships the issuers' public keys
  (yours, later the marketplace's); a valid signature shows "**Verified**: published by Jane Author via Spaced
  Positions" in the import preview and in the Collections tab. An unsigned pack can never claim `commercial`.
- **Enforcement in the official app**, for positions and games that came with a pack whose `rights.export` is false:
  left out of `:pack-export` and PGN export (with a note saying why), no multi-FEN copy; single positions can still be
  shown on a board and analysed (that is training). A lock icon and the holder's name show with them.
- **The licensee's own work** stays exportable where `share_analysis` allows: their comments and variations, without
  the pack's own texts.
- **Kept with the import**: `ReceivedPack` stores the licence object, the signature and the issuer, so the licence can
  be shown at any time (Settings → Packs).
- **Course licences** (`kind: "course"`): personal like a commercial one, issued by you for your students; no shop.
- Composition and the sharing choice of 12 §5–6 go into the same manifest.

Building format 2 needs: the licence object and signature fields (pack writer and reader), signature checking
(Ed25519 with the `cryptography` package, Apache-2.0, GPL-3.0 compatible), the export rules above, and a small signing
tool for you (`manage.py pack-sign <file> --licensee …`). It is milestone **M2** (§6).

## 3 · How authors submit packs

Start personal and simple; make it a process only when there are more authors than you can talk to.

1. **Agreement first**: a short contract template (what is licensed: the collection in this form; non-exclusive;
   price and royalty share; who may receive course copies; how corrections and withdrawals work; term and end).
2. **Making the pack**: the author builds it in Spaced Positions (Collect, Analyse, tags) and exports it with
   *for review*, which adds the composition (12 §5) and a self-check report to the file.
3. **Sending it**: at first by email or a shared folder; later an upload page on your website, with the agreement
   accepted online.

## 4 · The review: what "high quality" means

Every pack goes through the same steps, and the result is recorded with it (who reviewed, when, which version).

| Step | Who | What is checked |
|---|---|---|
| 1 · Automatic checks | a script (`manage.py pack-review`) | the file reads, positions are legal, every puzzle has a solution that the engine confirms (the solution move is the best by a clear margin; alternatives that also win are listed), no duplicates inside the pack, duplicates with the public lichess database listed (allowed, but disclosed), tags and difficulty filled in, texts present in the pack's languages |
| 2 · Rights | you | the author owns the material or has the publisher's permission, in writing; the sources are named |
| 3 · Content review | a reviewer (you at first) | solves a sample (all puzzles of a small pack, at least 30 or 10 % of a big one), reads the explanations, checks that the solutions teach what the tags say, notes unclear or wrong items |
| 4 · Test-solve | 3–5 players of the target level | difficulty and enjoyment: solved / missed per puzzle, time, "too easy / right / too hard"; the difficulty ratings are adjusted from it |
| 5 · Corrections | author | fixes from steps 1–4; a new version is reviewed only where it changed |
| 6 · Publishing | you | metadata (description, level, motifs, size, sample puzzles), the price, signing, the shop page |

A **quality score** (0–3 per criterion: correctness, explanations, tagging, difficulty, variety, presentation) is
kept per pack. Below a threshold the pack goes back to the author.

## 5 · The marketplace (sketch, for later)

- A shop on your website, not in the app: a catalogue, sample puzzles to try, the licence terms, payment (for
  Switzerland TWINT and cards, e.g. through a Swiss payment provider), and an account page with your packs.
- After payment the site issues a **personal, signed pack** (§2) for that buyer, to download and drop on the app.
  New versions of bought packs appear on the account page.
- The app stays offline and needs no account. Later an optional *Shop* link may open the website; the app never
  sends anything without being asked (09 §11).
- Legal and tax work before the first sale, with an advisor: the licence terms and author contracts (Swiss law on
  collections, URG; the EU database right for EU buyers), consumer law for digital goods, VAT (Swiss VAT once turnover
  passes the registration threshold; EU VAT on digital services sold to EU consumers, typically through the non-Union
  OSS scheme), invoices and bookkeeping, the privacy policy of the shop.

## 6 · Milestones: what has to be true before the next step

Each milestone has goals that are measurable without tracking anyone (counts people report, downloads, sales, the
voluntary test reports of 14 §5). Don't build the next step before the goals of the current one are met.

| | Milestone | Content | Goals before moving on |
|---|---|---|---|
| **M0** | **Test group** (now, 4–6 weeks) | the test version with the starter pack, packs from you (14) | 6–10 testers; every tester installs it and solves a first puzzle alone, in under 10 minutes; at least 5 still train in week 4; the top problems of 14 §7 fixed |
| **M1** | **Public beta** (3–6 months) | public releases, signed apps if possible, the website page, 12 steps 1–3 (collections, training and stats per pack) | 100 installs; 30 people training in a typical week; 40 % of new users still train in their second week; 3 coaches using packs with students; no data-loss bug for 3 months |
| **M2** | **Course packs** | pack format 2 (§2), signing, export rules; your course students get signed course packs; 12 steps 4–5 (composition, checks) | all students of 1–2 courses use it; 2 authors you know have signed an agreement; the review process (§4) done once end to end on one pack |
| **M3** | **Marketplace pilot** | the shop (§5) with 3–5 packs from 2 authors, legal and tax work done | 300 people training in a typical week; 50 sales; a review takes under 4 weeks; refunds and support manageable alone |
| **M4** | **Open to coaches** | the upload page, the review steps as a routine, author statistics | 1,000 people training in a typical week; enough reviewers (at least 2 besides you); the M3 packs rated well by buyers |

What not to do early: no shop before M2's course packs work (they test licences and signing with people you know),
no open submissions before the review has been done by hand several times, and no account or online feature in the
app at all unless a milestone really needs it.
