# Comparison Carousel renderer

Eight slides, Character 6, 1080x1920 JPG (9:16, so a reel shows the whole slide; Instagram
crops the sides off a 4:5 slide). A re-render keeps the pictures a row already has unless
`--repick` is passed. Rules come from the Jealousy Carousel Render
Blueprint (https://claude.ai/artifact/9CN9pvUkGhyQaiPBzNy5bb): TikTok Sans only, white text
with a drop shadow, hook centred on slide 1, story text at the bottom, no dots or numbers.

```bash
pip install -r requirements.txt
python3 render_comparison_carousel.py --carousel CC-0002 --all     # local preview in ~/.cache/comparison_carousel/out
python3 render_comparison_carousel.py --batch cc-20261107 --upload # render pending rows, upload, PATCH the table
```

Reads `public.comparison_carousel` (slide_1 = hook, slide_2..slide_8). Skips rows with
`status='rejected'`. Writes `slide_1_url..slide_8_url`, `source_images`, `render_status='rendered'`.
Key: `SUPABASE_ANON_KEY` or a service key, via `common/env`. Font: TikTok Sans variable file in
`~/Library/Fonts` (override with `CC_FONT_PATH`).

| Slide | Image |
| --- | --- |
| 1 | one of the 10 approved covers (`divorce-recovery-covers/manifest.json`) |
| 2 to 4 | food or atmosphere photos, plus exactly one Before photo in a random slot |
| 5 | Before photo, top left weight label |
| 6 | After photo, top left weight label |
| 7 and 8 | After photos |

Before slide 6 she only appears in Before photos. Labels read `Mon YYYY Nlb`, dates and weights
are seeded by the carousel id (Before month Nov 2025 to Apr 2026, After 3 to 6 months later,
After weight 146 to 150, about 7 lb per month back). Picks are distinct, least used first.
