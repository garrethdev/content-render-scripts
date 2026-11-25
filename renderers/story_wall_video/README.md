# Story Wall renderer (Character 6)

Content type `story_wall_video` (Garreth, 2026-11-25): an 8 second loop of one of her kitchen
clips with one whole story from `story_bank` on screen as a single paragraph. The text is on for
7 seconds and gone for the last second, so the video ends on just her and people watch it again
to finish reading. Silent file; the song name in `story_wall_posts.music` is added at posting.

```bash
pip install -r requirements.txt
# 1. make rows (picks clips and songs, marks the stories used)
python3 create_batch.py --batch sw-YYYYMMDD --stories 123,456,... --env-file ~/pm-dashboard/.env.local
# 2. render, upload, mark rendered
python3 render_story_wall.py --batch sw-YYYYMMDD --env-file ~/pm-dashboard/.env.local
python3 render_story_wall.py SW-003            # re-render one row
python3 render_story_wall.py --dry-run         # local files only
python3 render_story_wall.py --story 18847 --clip 12 --out out/test   # try a story, no table
```

- **Text:** the shared Character 6 look (`common/slide_text.py`: white Inter, black outline,
  colour emoji), centred, no tilt. The largest size that fits between 220 px from the top and
  430 px from the bottom in a 920 px column, never below 52 px. Garreth approved 53 px for a
  124-word story and turned down 46 px for 164 words, so a story is about 125 words at most;
  a longer one is refused and has to be cut first.
- **Shade:** a soft dark rounded patch just bigger than the text, 22 to 38% (each video its own
  strength, seeded by the content id, kept in `shade_pct`), gone with the text.
- **Story text:** `story_paragraph` collapses whitespace, joins the post title to the body with a
  full stop and drops Reddit's leading "NSV" tag. Words are not changed.
- **Clips:** `quote_video_clips` that are at least 8 s (white 1-8, 10-13, blue 28-33). Least
  used first, her face first; a blue clip and its white source count as one scene, never back
  to back. The shared use counter goes up when a post first gets a posting date.
- **Music:** a song name from the last 10 songs the trend refresh added to `music_library`
  (Garreth, 2026-11-25), least used first, never twice in a row; added at posting.
- **Checks:** every file is read back and must be 1080 x 1920 and 8 s before upload.
- **Storage:** `kitchen-character/story-wall-video/renders/<YYYY-MM-DD>/<content_id>.mp4`.
- **Keys:** the table has no public access, so a service key is needed even to read
  (`SUPABASE_SERVICE_KEY`, `CAROUSEL_SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY`).
