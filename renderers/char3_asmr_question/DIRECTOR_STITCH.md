# Char3 ASMR Question — Director Stitch (Blueprint)

The **director** for Char3 ASMR weightlifting-question videos. It does not render video.
It decides *how* each video is cut and writes that plan (a "blueprint") back to the hook
row. The local renderer (`render_char3_asmr_q.py`) later reads the blueprint and executes it.

- n8n workflow: **[Char3] ASMR Question — Director Stitch (Blueprint)**
- Workflow id: `HcMiA1ywOVhI20oh`
- URL: https://czed.app.n8n.cloud/workflow/HcMiA1ywOVhI20oh
- Supabase project: `qlcmgxgwpzmiebzxflai`

---

## What it does

1. **Run Director** (manual trigger) — run on demand from the n8n canvas.
2. **Set Limit** — sets `limit` (default **3**) = how many hooks to plan this run.
   Edit this node to plan more/fewer per run.
3. **Get Approved Hooks** — Supabase REST `GET /char3_asmr_hooks`
   filtered to `gate_status=eq.approved`, `used=is.false`, `blueprint=is.null`,
   ordered by `hook_no.asc`, `limit={{ Set Limit.limit }}`.
   Selects `id,hook_no,hook,payoff`.
4. **Get Clip Pool** — Supabase REST `GET /video_library`
   filtered to `content_label=eq.char3_weightlifting`, `phase=eq.After`
   (`executeOnce: true`, so it fetches the pool once regardless of hook count).
   Selects `storage_path,filename,tags`.
5. **Build Blueprints** — Code node (JS, run once for all items). For each hook row it
   builds one montage blueprint using a **deterministic pseudo-random generator seeded by
   `hook_no`** (mulberry32). No `Math.random()` — same hook always yields the same plan.
6. **Write Blueprint** — Supabase REST `PATCH /char3_asmr_hooks?id=eq.<id>` with body
   `{ "blueprint": <json> }` and header `Prefer: return=minimal`.

If Get Approved Hooks returns 0 rows, the downstream nodes simply don't run (nothing to do).

---

## Blueprint JSON schema

Written to `char3_asmr_hooks.blueprint` (jsonb):

```jsonc
{
  "total_target_sec": 21,        // integer 15-25, seeded by hook_no
  "beat2_at_sec": 2.17,          // float 1.8-2.6; payoff text fades in at this time (hook shows <3s first)
  "segments": [                  // ordered montage; each clip used at most once
    {
      "clip": "char3-weightlifting/after_stairs.mp4", // video_library.storage_path
      "in_sec": 0.87,            // trim start (seconds) into a mid-rep window (0.3-1.5)
      "len_sec": 3.89            // segment length (seconds), 2.5-4.5 (last segment trimmed to hit target)
    }
    // ... more segments
  ],
  "text": {
    "slide1": "<hook column>",   // beat 1 (question)
    "slide2": "<payoff column>"  // beat 2 (payoff)
  },
  "notes": "no clip repeated within a video; varied order seeded by hook_no; tightened to a mid-rep window; same-outfit clips grouped together for continuity"
}
```

### Rules the blueprint honors

- **No repeats** — each `storage_path` appears at most once per video (`used` Set guard).
- **Sums to target** — `sum(len_sec) ≈ total_target_sec`; the final segment is trimmed so the
  total does not overshoot.
- **Varied order per hook** — clip order is a seeded Fisher-Yates shuffle keyed off `hook_no`,
  so every hook gets a different, but reproducible, cut.
- **Outfit continuity** — clips are split into two outfit/era groups and each group is kept
  contiguous (grouped together), never interleaved:
  - **New "green" group**: `after_squat`, `after_barbell`, `after_stairs`
  - **Older group**: everything else (burgundy set / kitchen / etc.)
  A seeded coin flip decides which group leads.
- **Two-beat timing** — `beat2_at_sec` (1.8-2.6) keeps the hook alone on screen <3s before the
  payoff appears, matching the reference reel.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| `limit` | Set Limit node | Hooks to plan per run (default 3) |
| hook rows | `char3_asmr_hooks` | `gate_status=approved`, `used=false`, `blueprint IS NULL` |
| clip pool | `video_library` | `content_label=char3_weightlifting`, `phase=After` |

`char3_asmr_hooks` columns used: `id`, `hook_no`, `hook`, `payoff`, plus `blueprint` (write target).

---

## Nodes

`Run Director` (manualTrigger) -> `Set Limit` (set) -> `Get Approved Hooks` (httpRequest GET)
-> `Get Clip Pool` (httpRequest GET, executeOnce) -> `Build Blueprints` (code)
-> `Write Blueprint` (httpRequest PATCH).

---

## Credentials

All three HTTP nodes use **Authentication = Predefined Credential Type -> Supabase API**
(`nodeCredentialType: supabaseApi`). This injects both the `apikey` and
`Authorization: Bearer` headers that Supabase REST requires — a single httpHeaderAuth
credential cannot supply both, which is why the predefined Supabase credential type is used.

**Action required:** attach a `supabaseApi` credential whose host is
`https://qlcmgxgwpzmiebzxflai.supabase.co` and whose service key is
`CAROUSEL_SUPABASE_SECRET_KEY`, to all three HTTP nodes (Get Approved Hooks, Get Clip Pool,
Write Blueprint). The workflow was created referencing the existing
"Supabase Peptide Miracles Production" credential, but n8n did **not** auto-bind it, so the
credential dropdown on each HTTP node must be set manually (and verified to point at project
`qlcmgxgwpzmiebzxflai`). Never paste the raw key into node parameters.

---

## How the render script consumes the blueprint

`render_char3_asmr_q.py` is currently a single-clip proof (`local` mode). The blueprint is the
edit plan it will execute in DB mode:

- `blueprint.text.slide1` / `slide2` -> the two text beats (`beat1` / `beat2` args).
- `blueprint.beat2_at_sec` -> `C3Q_BEAT2_AT` (when the payoff fades in).
- `blueprint.segments` -> the montage: for each segment, trim the clip at `storage_path`
  starting at `in_sec` for `len_sec` seconds, then concat segments in array order. The
  existing warm grade, before-image inset, and silent audio bed are applied to the assembled
  montage exactly as in the single-clip path.
- `blueprint.total_target_sec` -> sanity cap on final duration.

Consumption sketch:

```python
bp = row["blueprint"]                       # jsonb from char3_asmr_hooks
parts = []
for seg in bp["segments"]:
    clip = download(seg["clip"])            # storage_path -> local file
    parts.append(trim(clip, seg["in_sec"], seg["len_sec"]))
montage = concat(parts)                      # in array order (no repeats guaranteed by director)
render(montage, before_img,
       beat1=bp["text"]["slide1"],
       beat2=bp["text"]["slide2"],
       beat2_at=bp["beat2_at_sec"])          # sets C3Q_BEAT2_AT
```

After a successful render, mark the hook row `used=true` and set `final_video`.

---

## Sample blueprint (hook #1)

Deterministic output for `hook_no = 1`
("When did you realize losing weight was about metabolic health?"):

```json
{
  "total_target_sec": 21,
  "beat2_at_sec": 2.17,
  "segments": [
    { "clip": "char3-weightlifting/after_stairs.mp4",  "in_sec": 0.87, "len_sec": 3.89 },
    { "clip": "char3-weightlifting/after_squat.mp4",   "in_sec": 0.93, "len_sec": 2.61 },
    { "clip": "char3-weightlifting/after_barbell.mp4", "in_sec": 0.94, "len_sec": 3.45 },
    { "clip": "char3-weightlifting/after_cablerow.mp4","in_sec": 1.36, "len_sec": 4.38 },
    { "clip": "char3-weightlifting/after_machine.mp4", "in_sec": 1.45, "len_sec": 3.47 },
    { "clip": "char3-weightlifting/after_legpress.mp4","in_sec": 1.13, "len_sec": 3.2 }
  ],
  "text": {
    "slide1": "When did you realize losing weight was about metabolic health?",
    "slide2": "Once I fixed my metabolism and kept training, the weight finally came off."
  },
  "notes": "no clip repeated within a video; varied order seeded by hook_no; tightened to a mid-rep window; same-outfit clips grouped together for continuity"
}
```

Note the green group (stairs, squat, barbell) is kept contiguous and leads, then the older
group (cablerow, machine, legpress) — continuity preserved, no clip repeated, segment lengths
sum to the 21s target.

---

## Notes / limitations

- **Not "active".** A manual-trigger-only workflow cannot be activated in n8n (activation needs
  a schedule/webhook/polling trigger). It is saved and run on demand via the Run button — this
  is the intended state, not an error.
- Deterministic by design: re-running on the same hook (before it is marked `used`) rewrites the
  same blueprint. Change `hook_no` seeding in Build Blueprints if you want re-roll behavior.
