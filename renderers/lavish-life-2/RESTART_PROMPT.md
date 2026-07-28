# Lavish Life 2.0 — Session Restart Prompt

Paste everything below this line into a fresh Claude session on any machine.

---

I'm continuing the **Lavish Life 2.0** project. Full state:

## The play
An AI character ("Character 3", a Black woman 30-45) lives a rich soft life in Instagram dump carousels → later, ONE casual Ozempic mention → viewers comment "build" → DM funnel. **Sequencing rule: the Ozempic mention and comment keyword come LAST and are currently hard-disabled everywhere. Get the machine right first.**

## Where everything lives
- **Code + docs:** github.com/garrethdev/content-render-scripts → `renderers/lavish-life-2/` (runners, stitcher, prompt JSONs, all research docs). Clone via deploy key (ssh host alias `github.com-contentrender` on the main machine).
- **Approved image library (public URLs):** Supabase bucket `lavish-approved` in project `qlcmgxgwpzmiebzxflai`:
  `https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/public/lavish-approved/<path>`
  - `sources/` — 15 user-approved REAL frames (the clone queue), descriptive names
  - `generated/` — 39 approved, iphoneified images (the posting pool)
  - `pending-roundc/` — 7 fresh clones awaiting my grading (roundc_60..66)
  - `MANIFEST.md` — provenance and rules
- **Data:** Supabase table `lavish_life_v2` (same project). n8n Scriptwriter workflow `nTrymbqf05ReBtFO` (built, active, NEVER executed):
  - Seed 28 hooks: `curl -X POST https://czed.app.n8n.cloud/webhook/4f231578-b7e6-4e06-8276-9bb27d4ba72a/lavish2-scriptwriter -H 'Content-Type: application/json' -d '{"mode":"seed"}'`
  - Script 5: same URL, `-d '{"mode":"script","count":5}'` (holds ~1-2 min, returns ids)
- **Character identity refs:** Character 3 face = `https://v3b.fal.media/files/b/0aa1d81b/BiDjTylnuIUX358IJGsSV_char3_car.png` (used as image ref in every generation). Boyfriend = text description only: "tall athletic Black man, short fade, neat short beard, natural matte skin" (canonical face image: `generated/dump_113.jpg` in the bucket).

## The workflow that works (hard-won, do not deviate)
1. **Source-frame-first.** Never invent scenes. Pick REAL frames from the muses' grids, get my approval, then clone: fal-ai/gpt-image-2/edit with `image_urls: [char3_ref, source_frame]`, prompt = "recreate the second image EXACTLY... replace the woman with the woman from the first image" + explicit lines preserving the LIGHTING and the GAZE directions (my two obsessions). Swap any man to the boyfriend description. Bikinis → one-piece same color.
2. **Muses:** shadesofpinck (primary; couple luxury), getawaybaes (pinned cruise set only), thedolcemimi (hands/tablescape dinner register). Rejected: solo-artsy grids (theikonickay ruled too artsy), invented group scenes (4 synthetic faces = AI tell), embrace/kissing comps.
3. **Filter map:** selfie-framed source images hard-block as input; "bikini"+face-ref flags (use one-piece); flagged calls don't bill; retry 3x, moderation is stochastic; fallback = forensic text-only prompt written from studying the frame.
4. **QA before I see anything:** view every generated image (contact sheets fine), kill anatomy/garble/face-drift silently.
5. **Iphoneify every still** (ffmpeg): `scale=1112:1976:lanczos, crop 1080:1920 +12x+8y, colorchannelmixer rr=.975 bb=1.03, curves 0/0.01 1/0.985, noise alls=9:allf=u`.
6. Text overlays go ON TOP after the pass (crisp app text over grainy photo). Hook style: white text, soft shadow, upper third — NOT pill bubbles. Cards: white/pastel camera-roll artifact, unbranded, lowercase, one per carousel max, closer slot default.
7. **Assembly:** `lavish_stitch.py` (in the repo) — spec JSON → slides + caption.txt.
8. Cost gate: show prompt+payload+cost, get my OK before billed submits (~$0.25/image, fal, FAL_KEY in my secrets env). Batch-track any content run.
9. **No ETAs. Work gate by gate.**

## Approved text assets (in repo docs/)
- `DUMP_HOOK_BANK.md` — 28 approved slide-1 hooks in the muse voice (never regen without my OK)
- `DUMP_HOOKMAKER.md` — the full text-layer system prompt (captions, cards, placement laws, confession rules — confession OFF)
- `SLIDE_COPY_PATTERNS.md`, `PATTERNS.md` — the research behind card design and image taste

## Open gates (my side)
1. Grade the 7 pending round-C clones (`pending-roundc/` in the bucket)
2. Grade the 4 Zepbound pen shots (guide-formula set)
3. Cull 5 near-duplicate variants in generated/
4. Fire seed + first script batch, review the 5 scripted rows
5. Pick the posting account
6. LAST: activate the Ozempic + "build" layer

Pick up wherever I point next.
