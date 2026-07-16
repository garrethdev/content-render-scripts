# peptide-renderers

Centralized, code-only repo of every content-type render pipeline. One place for
all the local renderers that were previously scattered across `~/Claude/*`.

**Code only — no data, no media, no venvs.** Each renderer reads its source rows
from Supabase (project `qlcmgxgwpzmiebzxflai`) and writes finished media to
Supabase storage. Nothing secret is hardcoded; everything loads from env via
[`common/env.py`](common/env.py).

## Content type → renderer

| Content type | Path | Entry point | Notes |
|---|---|---|---|
| Lavish / BWC / Informational carousel | `renderers/carousel/` | `render-carousel.js` | Satori+sharp image renderer. **Canonical copy is deployed from `carousel-command-center` on Vercel** — this is a mirror; edit there and re-sync. |
| Eye Covering carousel | `renderers/covered_eye/` | `covered_eye_carousel.py --supabase` | Cleanest CLI (`--batch`, `--render-set`, `--upload`, `--mark-rendered`). |
| Looksmaxxing / Glowup deck | `renderers/glowup/` | `make_glowup_decks.py` | ⚠ current script re-renders ALL decks; `render_glowup.py` has the `render_status=ready` filter. |
| Grandma BA / 2-slide BA video | `renderers/filler/` | `render_ba.py batch\|ba <prefix>` | Lives with filler (shares its modules). |
| Viral Filler video | `renderers/filler/` | `worker.py` (daemon) / `drain.py` / `queue_match.py` | The reference queue/worker system. |
| Embarrassed video | `renderers/embarrassed/` | `stitch_embarrassed.py [--content_id N]` | Status-queue driven. |
| Divorce Horror video | `renderers/divorce/` | `divorce_horror_render.py [DIV-###]` | Cleanest status-driven design; ffguard-wrapped. |
| Divorce title cards | `renderers/divorce_titlecards/` | `gen_titles.py` / `gen_v4_twoline.py` | fal-ai title-card image gen. |
| Conspiracy Grandma video | `renderers/conspiracy/` | `render_conspiracy.py --ids ... --prefix ...` | + `add_music.py`, `upload_videos.py` post-steps. |
| Dating Genre video | `renderers/dating/` | `scripts/run_pipeline.py --row-id N ...` | Clean per-video CLI; `batch_render.py` is the batch driver. |
| Carousel re-render driver | `renderers/carousel_rerender/` | `rerender_driver.py <rows.json> <log>` | Drives the deployed Vercel `/api/render-carousel`. |

**Not in this repo (no renderer exists yet):** Eat Whatever video, Peptide Question deck.
**BA main video** is a Claude-skill pipeline (Sheets-based), not a standalone script.

## Shared

- `common/env.py` — secret + config loader. `env.require("NAME")` / `env.get("NAME", default)`.
- `common/ffguard.py` — the render guard; wrap every ffmpeg call. Import as
  `from common.ffguard import run_ffmpeg_guarded` (renderers add the repo root to `sys.path`).
- `common/iphoneify.sh` — the approved iPhone-look post-process.

## Setup

```bash
cp .env.example .env      # fill in, OR rely on ~/.config/peptide-secrets/.env
```
`common/env.py` loads `~/.config/peptide-secrets/.env` first (so scripts run unchanged
on the original machine), then a repo-local `.env`. Both are git-ignored.

Most renderers use their own folder venv; `renderers/filler/requirements.txt` lists that
lane's deps. ffmpeg/ffprobe must be on PATH (or set `FFMPEG`/`FFPROBE`).

## Security

- **Pre-commit/pre-push guard:** `bash scripts/install-hooks.sh` once per clone — every commit
  and push is then scanned for credential-shaped content (Supabase/OpenRouter/Anthropic/GitHub/
  Slack/AWS key patterns, JWTs, private keys, staged `.env` files) and blocked on a hit.
- **No keys are committed.** All 5 formerly-hardcoded keys were moved to env loading; a
  full sweep confirms zero secrets in the tree. The `.gitignore` blocks `.env` and media.
- Two scripts were **deliberately excluded** from this repo and should be rotated separately
  (they held live keys and aren't renderers): `~/Claude/gen150.py` (service-role key +
  OpenRouter — also violates the "content only from n8n" rule) and
  `~/Claude/viral-filler-render-test/` (superseded prototype, 3 hardcoded keys).
- The anon/publishable key these scripts use is already public in the deployed dashboard,
  so it is low-risk, but rotating it is still worthwhile.

## Known follow-ups (not blockers for pushing code)

- Some output/asset paths still default to the original `~/Claude/<olddir>/…` locations
  (glowup `out/`, covered_eye char3 ref, conspiracy `music/`). They're env-overridable
  where they matter (conspiracy/divorce) and are scratch/output dirs elsewhere — update or
  override when you relocate the asset libraries.
- Var-name drift: the service-role key is read as both `CAROUSEL_SUPABASE_SECRET_KEY` and
  `SUPABASE_SERVICE_KEY` across scripts — `.env.example` sets both.
- Glowup: add the `render_status` filter before driving it from the orchestrator.
