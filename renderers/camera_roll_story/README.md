# Camera Roll Story renderer

Character 6, eight slide image carousel. Lane `camera_roll_story`, table
`public.camera_roll_story_carousel`, ids `CRS-0001` and up. Slides are 1080 x 1920 JPGs, per the
Carousel Render Blueprint.

## Files

| File | What it does |
|---|---|
| `pictures.py` | The picture plan: which kind of picture each beat gets, the layouts for slides 2 to 6, the reveal on slides 7 and 8. |
| `render_camera_roll_story.py` | The look (text, tint) and the picture picking. Renders a JSON file of stories to local JPGs. |
| `render_table.py` | Table mode: reads rows, renders, and with `--upload` saves the slides and marks the row rendered. |
| `schema.sql` | The migration that wired the lane. Applied to the live database on 2026-11-19; kept here as the record. |

## The story and its pictures

| Slide | Beat | Picture |
|---|---|---|
| 1 | Hook | Her before, with her body in the frame |
| 2 to 6 | Scene, turning inward, what she tried, a kind person mentions peptides, she starts | Mostly pictures with no person, plus one or two of her before. One of eight layouts, rotated per deck |
| 7 | The slow change | Her now, close or waist up |
| 8 | Closing scene | Her now, at full length |

A picture carries the mood of its beat, not the words of its line. A story whose slide 7 still has
her struggling sets `reveal_from` to 8, which holds the reveal for the last slide.

## Picture rules

- Every picture comes from `rich-life-images/character-6/`. The renderer refuses a picture stored anywhere else.
- The photo list is pulled fresh from `carousel_images` on every run, and each file is checked in storage before it is used, so a photo deleted from the library cannot come back.
- A photo is used at most three times in a batch.
- A row that already has `source_images` keeps its pictures on a re-render. `--repick` chooses again. A kept picture that has since been deleted stops that deck with a message.

## Text

White TikTok Sans with a drop shadow, a light tint over the whole picture (10 to 26 percent, lighter
on dark photos) and a soft dark glow behind the words. The hook is centred on slide 1; story text
sits at the bottom and ends 430 px above the edge.

## Run

```
pip install -r requirements.txt
python3 render_table.py                                   # pending rows -> ./out/<carousel_id>/, nothing saved
python3 render_table.py --upload                          # pending rows -> storage + row update
python3 render_table.py --batch crs-20261118 --all        # a whole batch again, in order
python3 render_table.py --carousel CRS-0003 --all --repick --upload
python3 render_camera_roll_story.py --stories stories.json --sheet    # local, from a file
```

Render a whole batch in one run. The three-uses limit is counted across the run, so picking for a
few rows on their own can give different pictures than picking for the batch.

Slides are uploaded to `rich-life-images/camera-roll-story/renders/<carousel_id>/slide_0N.jpg`.

## Settings (read through `common/env`)

| Name | Use |
|---|---|
| `SUPABASE_ANON_KEY` | Enough to read rows and the photo list |
| `CAROUSEL_SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_KEY` | Needed for `--upload` |
| `CR_FONT_PATH` | The TikTok Sans variable font. Default `~/Library/Fonts/TikTokSans[opsz,slnt,wdth,wght].ttf` |
| `CR_CACHE_DIR` | Where downloaded photos are kept. Default `~/.cache/camera_roll_story/src` |

## Not part of this renderer

The writer, captions, music and the content check are n8n workflows. The lane is wired at cadence 0
and a deck posts only after it is rendered, has a caption, passes the content check and is off Hold.
