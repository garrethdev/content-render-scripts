# Jealousy carousel renderer (Character 6)

Pillow renderer for the Jealousy carousel: six slides at 1080x1920, Character 6 telling how
someone close to her turned on her as she changed. Rows live in `jealousy_carousels`.

```
n8n writer + director (LNryf7UU2kxhfNvC) ──► jealousy_carousels (status='directed')
                                                   │
                                   stitch.py --batch <name> ◄── blueprint.json
                                                   │
                  rich-life-images/jealousy/<carousel_id>/slideN.jpg
                  PATCH slide_N_url, render_status='rendered', status='rendered', rendered_at
                                                   │
             n8n music selector (kLNyOF1qOjeygb9Z) ──► music
                                                   │
                     gate.py --batch <name> ──► gatekeep_status / notes, quality_status='ok'
                                                   │
         trigger sr_autoset_jealousy_carousels ──► scheduler_ready = true
```

## Setup

```bash
pip install -r requirements.txt
```

- Key: `SUPABASE_SERVICE_KEY` (or `CAROUSEL_SUPABASE_SECRET_KEY`) and `SUPABASE_URL`, in
  `~/.config/peptide-secrets/.env` or the repo `.env`, loaded by `common/env.py`.
  The publishable key will not work: `jealousy_carousels` has row level security with no
  policies, so only the service role can read or update it.
- Font: `assets/TikTokSans.ttf` (TikTok Sans variable font, SIL Open Font License in
  `assets/OFL.txt`). Slide 1 uses the Bold instance, the rest SemiBold. Override with
  `JEALOUSY_FONT_PATH`.

## Making a new batch

1. **Write and direct.** In n8n, open "Jealousy Carousel: Writer then Director (Character 6)".
   Set the new batch name in two places: the filter in "Get Used Sources" and the
   `batch:` value in "Finalize Rows". Run it. Each run tries every unused story (quality 8,
   then 7, then 6, one per source URL, up to 40) and keeps the ones that pass the story
   reviewer and the image QA as `status='directed'`. Run it again until you have enough;
   it skips stories already rendered or already passed in the batch. Rejected attempts are
   stored as `needs_fix` and are ignored by every step below.
2. **Number them.** Give the passing rows a `carousel_id` of `NN-<source_id>`, continuing
   from the last batch, so storage paths and posts are easy to tell apart (if left empty,
   `stitch.py` uses `<source_id>-<row id prefix>`):
   ```sql
   with b as (select id, row_number() over (order by created_at, id) + <last number> rn
              from jealousy_carousels where batch = '<batch>' and status = 'directed')
   update jealousy_carousels c set carousel_id = lpad(b.rn::text, 2, '0') || '-' || c.source_id
   from b where c.id = b.id;
   ```
3. **Render.**
   ```bash
   python3 stitch.py --batch <batch> --limit 25 --dry-run   # renders to ./out, touches nothing
   python3 stitch.py --batch <batch> --limit 25             # render, upload, update rows
   python3 stitch.py --ids <row uuid>,<row uuid>            # specific rows, even if already rendered
   ```
   Rows are picked when `status = 'directed'` and `render_status` is empty. A row with fewer
   than six slides or a missing photo is skipped and printed. Re-running a row overwrites its
   images in place (the objects are served `no-cache`).
4. **Music.** In n8n, "[Jealousy] Music Selector (OpenRouter)": set the batch in
   "Get Carousels" and run it. It only fills rendered rows with empty `music`.
5. **Captions.** The writer's captions are plain sentences. Posted batches use a lowercase
   line built on one small moment from the story, a short question, and four hashtags
   matched to who turned on her, for example
   `my sister canceled thanksgiving because i took my own purse back. sister thing? #sisterdrama #toxicfamily #jealousy #familydrama`.
   No ampersands or em dashes.
6. **Safety check.**
   ```bash
   python3 gate.py --batch <batch>                    # all rendered rows in the batch
   python3 gate.py --batch <batch> --only-unreviewed  # skip rows already gated
   ```
   Sends the carousels to the n8n Content Risk Gate (15 per call) and writes
   `gatekeep_status` (high = rejected, else approved), `gatekeep_notes`,
   `gatekeep_reviewed_at` and `quality_status = 'ok'`. Run it after captions are final:
   once a row has six slide URLs, music, a caption and an approved gatekeep, the database
   trigger sets `scheduler_ready = true`.

## Files

| File | What it does |
| --- | --- |
| `stitch.py` | Reads rows, renders, uploads, updates. |
| `renderer.py` | Drawing code. Change the look in the blueprint, not here. |
| `blueprint.json` | Canvas, text sizes and positions per slide, overlay, face blur, and the dated weight labels on slides 5 and 6. |
| `gate.py` | Content risk gate (step 6). |

## Layout (blueprint.json)

- 1080x1920. Photos are cover-cropped to fill the frame, anchored 35% from the top.
- Slide 1 (the line the villain said): text centered, Bold, with the friend's face blurred
  using the `blur_box` the director stored.
- Slides 2 to 6: text at the bottom, 430 px up so the app's buttons and caption do not cover
  it. White text with a soft shadow, no backdrops, no progress dots.
- Slides 5 and 6 carry a plain white date and weight label at the top left, 230 px down.
  Dates and weights are derived from the carousel id, so re-renders are stable.
- `renderer.py` also supports `"fit": "blur_fill"` under `canvas` (full-width photo over a
  blurred copy of itself). Not used; the default is the crop.

## Image pool

Photos come from `jealousy_image_pool` by role: slide 1 `friend`, slide 2 `pensive`,
slides 3 to 5 `old_body`, slide 6 `new_body`. The director picks by description. The pool
has 3 friend photos and 1 pensive photo, so slides 1 and 2 repeat across carousels; add
more of both to vary them.

## History

- Nov 4, 2026: batch `jealousy_v2_2026_11_04` (ids 01 to 25) rendered at 1080x1350.
- Nov 6, 2026: canvas moved to 1080x1920 with story-safe margins. Batches
  `jealousy_v2_2026_11_04` and `jealousy_v3_2026_11_05` (ids 26 to 50) re-rendered at 9:16.

The Jealousy lane is not registered in the scheduler on purpose; nothing here schedules or posts.
