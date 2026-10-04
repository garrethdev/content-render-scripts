# Leanne Transformation Carousel renderer

Pure Pillow renderer for Character 6 (Leanne) weight-loss / anti-aging
**transformation-reveal** carousels for women over 40. Burns the pre-approved,
already-humanized copy onto landscape backgrounds; the final slide is a real
reveal photo. It never writes copy (copy comes from the 3-call writer: hook ->
body -> humanizer).

## Source
- Table: `public.leanne_transformation_carousel` (Supabase `qlcmgxgwpzmiebzxflai`).
  Reads `slide_1..slide_6` (copy) and `slide_1_url..slide_6_url` (images).
  Pulls `approved = true` and `rendered_at IS NULL` unless flags say otherwise.
- Backgrounds: `public.carousel_images`, Character 6 approved set in bucket
  `rich-life-images`:
  - **general pool (slides 1..n-1):** `atmosphere` (7) + `food` no-person (30) +
    up to `HER_IN_GENERAL` (12) `her` lifestyle shots, all from
    `carousel-basis/2026-09-20`.
  - **reveal (final slide):** one real `her` photo from the same after batch.
  - A `before` pool (`before-basis/2026-09-26`, her/before) is fetched and
    available but not used in the default layout (owner chose: only the last
    slide is a reveal photo). Wire it in if you later split the reveal.
- Tag JSON spacing is inconsistent across batches, so category/stage are parsed
  in Python (`_tag`), not via SQL ilike.

## Output
- Renders 1080x1350 JPGs to `out/<carousel_id>/slide_0N.jpg` + a `filmstrip.jpg`.
- With `--upload`: uploads to bucket `leanne-carousel-images`
  (`renders/<id>/slide_0N.jpg`), writes `slide_N_url`, `source_images`,
  `status='rendered'`, `rendered_at`.

## Usage
```
# local render only (no writes) — good for QA
python3 render_leanne_transformation.py --supabase --carousel LEA-B1-10 --include-unapproved

# render + upload every approved, not-yet-rendered carousel
python3 render_leanne_transformation.py --supabase --upload

# one row, or ignore the rendered_at filter
python3 render_leanne_transformation.py --supabase --carousel LEA-B1-10 --upload
python3 render_leanne_transformation.py --supabase --all
```

Secrets from `~/.config/peptide-secrets/.env`: `CAROUSEL_SUPABASE_PROJECT`,
`CAROUSEL_SUPABASE_SECRET_KEY`. Needs `pillow` and `requests`.

## Notes / open
- Background supply is thin: only 7 `atmosphere` images, so the general pool
  leans on food + a few her shots. Generate more `atmosphere` images to reduce
  repetition across carousels.
- An existing `slide_N_url` on a row is respected, so a hand-picked reveal photo
  can be set per carousel and the brain will not overwrite it.

## Pull everything (latest copy from the database)
Regenerates every Leanne carousel from the live `leanne_transformation_carousel` table, so the output is always the latest copy. A read-only key is enough:

```bash
git pull origin main
cd renderers/leanne_transformation
SUPABASE_KEY=<project anon key> python3 render_leanne_transformation.py \
  --supabase --all --include-unapproved --out ~/leanne_latest
```
Output: `~/leanne_latest/<carousel_id>/slide_01..06.jpg` (+ `filmstrip.jpg`) and `~/leanne_latest/manifest.json`
(copy, captions, hashtags, files). ~75 s for all 40 carousels. The anon key is in Supabase Dashboard, Project Settings,
API Keys (project `qlcmgxgwpzmiebzxflai`). Backgrounds are seeded by `carousel_id`, so re-pulls are stable.

`--upload` (store the renders in the `leanne-carousel-images` bucket and write `slide_N_url` back) additionally needs the
service/secret key as `CAROUSEL_SUPABASE_SECRET_KEY`.
