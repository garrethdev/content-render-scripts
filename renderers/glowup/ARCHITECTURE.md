# Glow-Up Deck Architecture (decided 2026-07-31)

One brain, one painter, one source of truth. Written after a day of the local
renderer and the n8n Director drifting apart and producing different layouts.

## The three pieces

### 1. GitHub — source of truth
Repo `garrethdev/content-render-scripts`, `renderers/glowup/`.
Holds both files that define the lane:
- `make_glowup_decks.py` — the renderer (the painter).
- `deck_rules.json` — the layout rules the Director reads (pool→slot mapping,
  2+2 diagonal, brightness-match tolerance, date format, fixed copy lines).

Nothing is authoritative unless it is on `main`. Local edits are not real until
pushed.

### 2. The Director (n8n) — the brain
Reads `deck_rules.json` from GitHub (raw URL) + the image bank + the deck copy.
Makes EVERY creative decision and writes ONE complete manifest per deck into
`glowup_decks.render_manifest`. The manifest is fully resolved — no choices left:

```
{
  "deck_key": "...",
  "slides": [
    { "n": 1, "layout": "quad",   "text": "<hook>",        "cells": [url,url,url,url] },
    { "n": 2, "layout": "single", "text": "<before_line>", "cells": [url] },
    { "n": 3, "layout": "quad",   "text": "<tip_face>",
      "cells": [url_TL, url_TR, url_BL, url_BR] },   // positions already decided
    ...
    { "n": 7, "layout": "single", "text": "<after>", "datestamp": "July\n2026",
      "cells": [url] }
  ],
  "suggested_sound": "..."
}
```

Every image is a concrete URL in a concrete corner. Diagonal pairing, brightness
matching, category spread, date — all resolved HERE, by the brain, once.

### 3. The renderer (local Python) — the painter
Runs on the Mac. Does exactly four things and makes ZERO decisions:
1. `git pull` at start of run — so it is byte-identical to GitHub every time.
   (Removes the whole "keep local and repo in sync" problem: sync is automatic.)
2. Read `render_manifest` for each pending deck.
3. Paint each slide literally: download the listed cells, place them in the
   listed corners, burn the listed text, stamp the listed date.
4. Upload slides, set `render_status='rendered'`.

If a deck looks wrong, the fix is in the Director's decision or `deck_rules.json`
— NEVER in the renderer. The renderer has no layout logic left to be wrong.

## Flow
```
edit deck_rules.json / renderer  ->  push to GitHub (source of truth)
        |                                   |
   Director reads rules            renderer git-pulls at run start
        |                                   |
   writes full manifest  ---------->  paints manifest literally  -> Supabase slides
```

## Why this kills the drift
- Two implementations of the layout logic collapse to one (the Director).
- The renderer can no longer disagree with the Director — it obeys the manifest.
- Local can no longer disagree with GitHub — it pulls before every run.
- Changing a rule = edit one JSON file, push. Both sides pick it up automatically.

## Migration (current -> this)
1. Extract the layout rules now living inside `make_glowup_decks.py` into
   `deck_rules.json`. Commit both.
2. Move ALL image-selection + placement decisions out of the renderer and into
   the Director's manifest builder. Renderer loses its `pair()`, `matched_pair`,
   pool logic — keeps only download/place/text/upload.
3. Add `git pull` to the renderer's start (pattern already used elsewhere via
   `renderer_env.sh`).
4. Point the Director at the raw GitHub URL for `deck_rules.json`.

## Out of scope (user decision 2026-07-31)
No automated output-QA layer. Correctness of the finished slides is checked by
eye, not by a qa script.
