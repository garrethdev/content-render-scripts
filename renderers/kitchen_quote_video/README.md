# Kitchen Quote Video renderer (Character 6)

Content type `kitchen_quote_video`: a Character 6 kitchen clip with one short line on screen
over a dark fade, 1080 x 1920, silent (the song name in `quote_video_posts.music` is added at
posting).

```bash
pip install -r requirements.txt
python3 render_kitchen_quote_video.py                     # rows waiting to render
python3 render_kitchen_quote_video.py --batch <batch>     # one batch
python3 render_kitchen_quote_video.py KQV-B-01            # rerender named rows
python3 render_kitchen_quote_video.py --dry-run           # render to ./out, no upload, no row changes
```

- **Rows:** `quote_video_posts`. Without names or `--batch` it takes rows whose `render_status`
  is empty, `pending` or `failed` and that have `hook_text`. After a render it sets `video_url`,
  `local_file`, `render_status = rendered`, `rendered_at`, and fills `clip_no`, `shirt_color`
  and `music` when they were empty. A failed row gets `render_status = failed` and `render_error`.
- **Clips:** every active row in `quote_video_clips`, white shirt (1 to 27) and dusty blue
  (28 to 33). New rows get the least used clip, her face first. A blue clip and the white clip
  it came from count as one scene: one run does not repeat a scene until the others have had
  a turn and never puts it back to back. When a white clip and its blue version are tied, the
  shirt with fewer posts wins. `--shirt blue` or `--shirt white` limits new picks.
- **Music:** a row without a song gets the least used active `music_library` song tagged
  `kitchen_quote_video`, never the same song twice in a row.
- **Look:** the same overlay as the 21 live videos (2026-11-24 rerender): TikTok Sans Bold 64 px,
  white with a drop shadow, centred in a 912 px column, last line 430 px above the bottom, black
  fade from 420 px above the text to 72%, Apple emoji. The blue clips are 704 x 1248, so they get
  a light sharpen after the upscale.
- **Checks:** each output is read back and must be 1080 x 1920 and the clip's length (10 s max)
  before it is uploaded.
- **Storage:** `kitchen-character/kitchen-quote-video/renders/<YYYY-MM-DD>/<video_id>.mp4`.
- **Assets:** the font and emoji pictures are not in git. `assets.py` takes them from
  `kitchen-quote-video/renderer/kqv_renderer_2026-11-24.tgz` in storage on first use and keeps
  them in `./cache/`; an emoji missing from that kit is fetched from the same Apple set.
- **Keys:** `SUPABASE_URL` and a service key (`SUPABASE_SERVICE_KEY`, `CAROUSEL_SUPABASE_SECRET_KEY`
  or `SUPABASE_SERVICE_ROLE_KEY`) through `common/env.py`, or `--env-file <path>`. `--dry-run`
  reads with `SUPABASE_ANON_KEY`.
