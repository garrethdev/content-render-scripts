# Viral Theories carousel renderer

Pillow version of the Figma template "Viral Theories Carousel Template"
(file `yw1p6G09rkMIN6HdY5wIJ3`, section `1:35`). It reads written copy from
Supabase, picks Character 6 images, renders 6 slides at 1080x1920, uploads them
and writes the URLs back to the row.

```
viral_theories_carousel (approved, rendered_at IS NULL)
  └─ slots JSON ──► render_viral_theories.py ◄── carousel_images (character-6-approved-%)
                        │
                        ├─ rich-life-images/viral-theories/renders/<VT-id>/slide_0N.jpg
                        └─ PATCH slide_N_url, source_images, rendered_at, status='rendered'
```

## Setup

```bash
pip install -r requirements.txt
```

- `schema.sql` is the table as applied to Supabase. `seed/` has the approved copy
  that VT-001 to VT-003 were seeded from.

- `CAROUSEL_SUPABASE_SECRET_KEY` (or `SUPABASE_SERVICE_KEY`) in
  `~/.config/peptide-secrets/.env` or the repo `.env`.
- Gotham Medium is licensed, so it isn't in this repo. The renderer looks for it at
  `~/Library/Fonts/Gotham-Medium.otf`. Set `VT_FONT_PATH` if yours is elsewhere.
- The first run downloads the rembg `u2net_human_seg` model (~170 MB). Cutouts and
  source images are cached in `~/.cache/viral_theories` (`VT_CACHE_DIR`).

## Run

```bash
python3 render_viral_theories.py                                # approved + not rendered
python3 render_viral_theories.py --carousel VT-001 --include-unapproved   # local preview
python3 render_viral_theories.py --batch <batch> --upload --brand "<product name>"
python3 render_viral_theories.py --carousel VT-001 --all --upload        # re-render
```

`[brand]` in the copy is replaced by the row's `brand` column, then `--brand`, then
`VT_BRAND`. `--upload` refuses to run while it's unresolved, unless you pass
`--allow-placeholder`.

## Row contract

`slots` is the writer's output:

```json
{"hook_lines": ["5 viral theories", "that will", "ACTUALLY", "change your body"],
 "hook_sub": ["(from a lifelong", "yo-yo dieter)"],
 "theories": [{"title": "1. the food noise theory.", "body_1": "...", "body_2": "..."}, "... x5"],
 "plug_theory": 3, "caption": "..."}
```

A slide whose text block is taller than 1700px fails that row, which means the copy is over its limits.

## Image rules

| Slide | Pool | Treatment |
| --- | --- | --- |
| 1 | Subject alone, `After`. Mirror/full-body shots first; no close, tight or overhead shots; cutout must cover 6–75% of the frame | 120% zoom, blurred and darkened background, sharp rembg cutout of her on top |
| 2–5 | `has_subject = false` (food, scenery) | Cover-fit, ×0.62, darker still if the text zone is bright |
| 6 | Subject alone, `After` | Same as 2–5 |

Picks are distinct within a carousel, least-used across the table first (from
`source_images`), and seeded by `carousel_id` so a re-render gives the same picks.
Portrait images (w/h ≤ 0.85) come first; squares are only a fallback.

## Fidelity

Checked against the Figma exports: slide 2 mean abs diff 6.7/255 with identical
line breaks, and slide 1 7.5/255 when rendered from the same photo.
