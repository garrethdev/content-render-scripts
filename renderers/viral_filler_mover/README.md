# Viral Filler — Moving Cutout (v0.0.1)

New filler format that replaces the split-screen top/bottom stack.

**Old:** 1080x1920 split into two cells — character loop on top, filler clip on bottom, hook at the seam.
**New (this):** the filler clip fills the **whole** frame and keeps its audio; a background-removed
**character cutout** (Char 2/3/4) nodding along **drifts around** the frame; a caption is burned
top-center for the first ~2.6s. Start position + drift path + caption jitter are **seeded**, so no
two renders are pixel-identical (duplicate-strike safety).

## The blueprint pieces (all swappable)

| Piece | How to swap |
|-------|-------------|
| **base** | any filler clip — `--base <path or URL>` (pull from `filler_library`) |
| **character** | `--character char3` — key into the `CHARACTERS` registry (alpha `.webm` cutout) |
| **placement** | `--placement roam_bottom` — a named roaming zone (`roam_bottom/right/left/free`) |
| **caption** | `--caption "..."` — the on-video "textbook" text |
| **seed** | `--seed 7` — drives start position + drift + caption jitter → uniqueness |
| **cut-h-frac** | cutout size as a fraction of frame height (default 0.36) |

## Render one video
```bash
python3 filler_mover.py \
  --base assets/base_7369650019848260906.mp4 \
  --character char3 --placement roam_bottom --seed 7 \
  --caption "watching her explain how she stopped dieting and just ate real food" \
  --out work/PROOF_char3_seed7.mp4
```
Or from a blueprint JSON: `python3 filler_mover.py --blueprint video.json` (same keys as the flags).

To make N unique videos from the same base+character, just vary `--seed` (and the caption wording).

## Assets (canonical home = Supabase, not git)
Binary assets are **git-ignored** (this is a code repo). The character cutouts are the durable
deliverable and live in Supabase project `qlcmgxgwpzmiebzxflai`:

| Asset | Where |
|-------|-------|
| Character cutouts (char2/3/4 `*_cutout.webm`) | table **`nod_cutouts`** → bucket **`nod-cutouts`** (public). `public_url` per row. |
| base filler clips | table `filler_library` (`source_video_url` → `viral-filler` bucket) |
| `hook-font.ttf` | copied from `dating-reaction/assets` (TikTok Sans ExtraBold) |

Pull the three cutouts locally before rendering:
```bash
for c in char2 char3 char4; do
  curl -sfL "https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/public/nod-cutouts/${c}_cutout.webm" \
    -o "assets/${c}_cutout.webm"
done
```

## Dependencies
- `ffmpeg`/`ffprobe` with libvpx-vp9 (alpha decode), Pillow, and — for minting — `rembg`+`onnxruntime`.
- `probe_base.py` calls scripts under `~/Claude/dating-reaction/scripts/` (face/motion solve, cutout mint).
  Override that path with `DR_DIR=/path/to/dating-reaction`.

## Minting a new / replacement character cutout
All three characters already exist in `nod_cutouts`. To add or replace one, background-remove a nod loop
into a VP9-alpha webm, upload it to the `nod-cutouts` bucket + upsert its `nod_cutouts` row, and register
the local path in `CHARACTERS` in `filler_mover.py`:

```bash
pip install rembg onnxruntime --break-system-packages
python3 ../dating-reaction/scripts/make_cutout.py \
  <character_nod_clip.mp4> assets/char2_cutout.webm <START> <END> 608 12
```
`make_cutout.py` runs rembg (u2net_human_seg) per frame and writes yuva420p VP9. A **clean nod loop**
(character nodding lightly, plain background) mattes best. Generate one on Higgsfield if needed
(image→video from a character reference), then cut ~3s of the nod.

## Notes
- Font: `assets/hook-font.ttf` (TikTok Sans ExtraBold), matches the existing filler hook style.
- Audio: base kept, `loudnorm=I=-14` applied. Output: CFR 30, yuv420p, +faststart (IG/TikTok-safe).
- The cutout is decoded with `-c:v libvpx-vp9` so its alpha survives — required.
- Zones avoid the top ~18% so the cutout never sits under the caption.
