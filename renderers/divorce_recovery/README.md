# Divorce Recovery carousel renderer

Pillow version of the Figma template for the Divorce Recovery carousel (file
`y6FFRRkbtlwBD2SnZojelO`, Batch 1 frames `1:2`, `1:728`, `1:878`, `1:885`, `1:892`,
`1:899`). Character 6, six slides at 1080x1920.

```
n8n writer (MLp2no3qGDAcDuLD) ──► ingest_decks.py ──► divorce_recovery_carousel (render_status=pending)
                                                          │
                                         render_divorce_recovery.py ◄── image pools (below)
                                                          │
                     rich-life-images/divorce-recovery/renders/<DRC-id>/slide_0N.jpg
                     PATCH slide_N_url, source_images, render_status='rendered', rendered_at
```

## Setup

```bash
pip install -r requirements.txt
```

- `schema.sql` is the table as applied to Supabase.
- Key: `SUPABASE_SERVICE_KEY` (or `CAROUSEL_SUPABASE_SECRET_KEY`), or `SUPABASE_ANON_KEY`,
  in `~/.config/peptide-secrets/.env` or the repo `.env`. The table and the
  `rich-life-images` bucket allow the publishable key.
- Fonts are not committed. Text uses TikTok Medium (`DR_FONT_PATH`, default
  `~/Library/Fonts/TikTokDisplayMedium.otf`); the lock screen uses SF Pro, SF Pro Text
  and SF Pro Rounded from `DR_SF_DIR` (default `/Library/Fonts`).
- rembg is optional. With it, slides 3, 5 and 6 check where her head is before placing
  the text; without it the text sits low on those slides.

## Run

```bash
python3 ingest_decks.py --decks 5                       # writer -> 5 new rows
python3 render_divorce_recovery.py                      # pending rows -> local preview
python3 render_divorce_recovery.py --upload             # pending rows -> storage + PATCH
python3 render_divorce_recovery.py --carousel DRC-0001 --all --upload   # re-render one
python3 render_divorce_recovery.py --deck-file writer_run.json --out ./out   # no database row
```

Decks the writer flags `needs_review` are inserted with `render_status='review'` and are
not rendered until someone sets them back to `pending`.

## Row contract

`deck` holds the writer's deck as returned. The renderer reads the flat columns:

| Column | Slide | Example |
| --- | --- | --- |
| `slide_1` (`hook_text`) | 1 | Eleven years. Done on a Tuesday. Now he wants a favour. |
| `sender_name`, `message_time`, `his_text` | 2 | Mark, 9:47 PM, "hey, hope ur ok. so steph and I..." |
| `slide_2` | 2 | He wants me to tell our son. (her line under the notification) |
| `slide_3` … `slide_6` | 3–6 | one line each |
| `caption`, `music` | post | caption from the writer; song from `music_library` |

## Image rules

| Slide | Pool | Rule |
| --- | --- | --- |
| 1 | `character-6/divorce-recovery-covers/manifest.json` | approved expression covers |
| 2 | wallpaper: After, her alone, portrait/selfie/mirror first; contact: `divorce-recovery/contacts/` | iOS lock screen with his Messages notification |
| 3 | After, her alone | not a selfie, not a mirror shot, not a close-up; full-body/environmental first |
| 4 | `scenery/` | no people, no food |
| 5 | Before | always a Before photo |
| 6 | After, her alone | selfies allowed |

After/Before photos come from `carousel_images` (`filename like 'character-6-%'`).
Picks are distinct within a carousel, least-used across the table first (from
`source_images`), seeded by `carousel_id` so a re-render gives the same picks. Portrait
images (w/h ≤ 0.85) come first.

Lock-screen date is a random 2026 date seeded by the carousel id; the clock shows the
time on his message.
