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

## Minting a new character cutout (char2 / char4)
Only `char3_cutout.webm` ships today. To add another character, background-remove a nod loop of that
character into a VP9-alpha webm, then register the path in `CHARACTERS` in `filler_mover.py`:

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
```

---

## Batch pipeline (`batch/`)

Added 2026-08-19 with batch VFM-B1-0819 (100 videos). The renderer above makes ONE video;
this turns it into a batch.

| Stage | Script | Notes |
|---|---|---|
| pick + screen bases | `screen_bases.py`, `screen_candidates.py` | Gemini vision: does the clip already carry its OWN text in the top third? 1 call per BASE, not per video. Candidates are screened straight off Supabase storage via `ffmpeg -ss` range reads (~2s), nothing downloaded until it passes. |
| hooks | `fetch_hooks.py`, `retry_hooks.py` | n8n Filler Hookmaker `oWh52PZu77pcjHaS`. Chunk 10 clips/call — the Code node has a 60s cap and the LLM node truncates past ~40 hooks. |
| download / probe / render | `run_batch.py download\|probe\|render\|status` | Each stage resumable; existing outputs are skipped. |
| render an explicit plan | `render_plan.py plan.json [workers]` | Used for replacement passes. |
| QA | `qa_batch.py`, `requa.py` | Gemini frame QA. See the prompt warning below. |
| validate | `validate.py` | ffprobe every file + decode the last second to catch truncated tails. |
| publish | `publish.py upload\|rows`, `run_captions.py` | Upload to the `viral-filler` bucket, insert `viral_filler_content` rows, then fill posting captions. |
| contact sheet | `grid.py [N] [out.png]` | Random visual grid for eyeball review. |

### Hard-won gotchas

- **Only ~42% of `filler_library` clips have a clear top third.** Budget ~2.5 screened clips per usable base.
- **Hook placement must respect `caption_bands`, not just the face.** The original bug: the fit loop only
  tested `face["top"]` and `choose_hook_y_frac` returned `0.05` unconditionally, so our hook landed on the
  clip's own text whenever the face sat low. Fixed — placement clears face AND text at every branch, and
  returns `None` (skip the hook) when nothing is safe. Never double-hook.
- **QA prompt: describe the cutout as PHOTOREAL.** Calling it "cartoon-style" made Gemini fail 19 videos for
  "cutout missing". It also calls the character's black clothing, and dark background regions of the base clip
  behind her, a "rectangular black box". Zoom every box/missing flag before believing it — on VFM-B1-0819,
  ~3 of 29 flags were real.
- **Do NOT pass `viral-content-filler-creator/caption_config.json`.** It still carries the `Type QUIZ in the
  comments` CTA that the 2026-08-07 ban-remediation patch added to Caption Maker's baseline banned list;
  passing it rejects every caption. Fire with source + output only and take the safe defaults.
- **Storage writes need the service key**, not the publishable key (`.env` in `viral-content-filler-creator`).
- Probe is the expensive stage: ~4.5 min/clip at 6 workers on an 8-core box, and load average hits ~14.
  Do not raise the worker count.

Nothing in `batch/` holds secrets; all keys are read from the environment or that `.env`.
