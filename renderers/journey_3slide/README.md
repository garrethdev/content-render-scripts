# 3-Slide Journey Carousel (Character 6)

Pillow port of the Figma "3-Slide Journey Carousel" template (`ZqDGTufoZyJX3EnRvdJyVi`).

| Slide | Content |
|---|---|
| 1 | Character 6 **before** photo + hook, a variation of "I'm gonna lose some weight" |
| 2 | Constant "Directed by ROBERT B. WEIDE" card |
| 3 | Character 6 **after** photo |

- **Data:** `public.journey_3slide_carousel` (`schema.sql`). Per row: `hook_text`, `hook_center_x`, `hook_top_y`,
  `before_image_url`, `after_image_url`. Outputs: `slide_1_url`..`slide_3_url`, `render_status`.
- **Images:** `rich-life-images/character-6/before-basis/` (before) and `.../carousel-basis/` (after).
- **Slide 2 constant:** `carousel-renders/journey-3slide/_assets/slide2_directed_by.png` (not committed; override with `JOURNEY_SLIDE2_URL` or a row's `slide_2_source_url`).
- **Font:** Gotham Bold is licensed and not committed. Set `JOURNEY_FONT_PATH` or install to `~/Library/Fonts/Gotham-Bold.otf`.
- **Env:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (via `common/env.py`).

```bash
pip install -r requirements.txt
python render_journey_3slide.py --dry-run     # writes ./out, no uploads
python render_journey_3slide.py               # render + upload + write back all pending rows
python render_journey_3slide.py J3-005        # one row
```

`scheduler_ready` flips automatically (DB trigger) once all 3 slide URLs, a caption, `render_status='rendered'`
and `gatekeep_status='approved'` are set. Scheduling registration (registry row, character mapping, views)
is not part of this renderer.
