"""Orchestrator: pool -> per-clip pipeline -> Supabase. One video per clip.

Per clip: download -> analyze (manifest) -> detect existing text -> (hook or hide) -> render -> upload -> record.
If the clip already has a burned-in hook, ours is hidden; otherwise one Claude hook is burned. Idempotent.
"""
import os, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import config, supa, media, hookscan, hooks

# Optional batch id stamped onto every podcast_renders row so a set of renders is
# traceable as one batch (mirrors the main filler pipeline's `batch` tag). Set via
# --batch or POD_BATCH; None leaves the column NULL.
BATCH = os.environ.get("POD_BATCH") or None

def process_clip(index, clip):
    """Run one clip end-to-end. Returns the public render URL, or None on skip/failure."""
    vid = clip["video_id"]
    character = config.CHARS[index % len(config.CHARS)]
    seed = index * 7 + 1
    print(f"\n[{index+1}] {clip['show']} {vid} :: {(clip.get('title') or '')[:55]}")

    base = media.download(vid, clip["url"])
    if not base:
        print("   download FAIL, skip"); return None

    duration = media.probe_duration(base)
    manifest = media.make_manifest(base)                       # analyzed once, cached on disk
    cached = clip.get("has_onscreen_top_text")
    if cached is None:
        has_text, why = hookscan.detect(base, duration)         # vision-OCR + speech-match, once per video
        print(f"   hook-detect: {has_text} ({why})")
    else:
        has_text = cached                                       # reuse stored result, skip re-analysis
        print(f"   cached hook-detect: {has_text}")

    if has_text:
        caption, hook_used = "", None
        print("   existing hook in opening -> hide ours (captions/late text do not trigger this)")
    else:
        # prefer an approved/previewed hook; only generate if none was stored
        hook_used = clip.get("proposed_hook") or hooks.gen_hook(clip.get("title", ""), clip.get("show", ""))
        hook_used = hooks.scrub(hook_used)          # final compliance guard: no GLP/peptide/drug terms
        caption = hook_used
        print(f"   clean -> our hook: {hook_used!r}")

    out = os.path.join(config.OUT, f"{vid}.mp4")
    if not media.render(base, character, seed, caption, out, manifest):
        print("   render FAIL"); return None

    url = supa.upload_video(out, f"podcast/{vid}.mp4")
    row = {"clip_video_id": vid, "show": clip["show"], "host": clip["host"],
           "hook": hook_used, "variant": 1, "character": character,
           "seed": seed, "render_url": url, "status": "done"}
    if BATCH:
        row["batch"] = BATCH
    supa.insert_render(row)
    supa.patch_clip(vid, {"status": "staged", "has_onscreen_top_text": has_text})
    print(f"   char={character} our_hook={'no' if has_text else 'yes'} -> {url}")
    return url

def _safe(index, clip):
    """process_clip wrapper: one bad clip must never kill the batch (or a pool worker)."""
    try:
        return process_clip(index, clip)
    except Exception as e:
        print(f"   [{index+1}] SKIPPED after error: {type(e).__name__}: {e}")
        return None

def run(limit, concurrency=None):
    """Render `limit` clips. With concurrency>1, clips run in a thread pool so one
    clip's network/API waits (download, Gemini vision, Whisper, upload) overlap
    another clip's CPU-bound ffmpeg encode. The encode itself is already multi-core,
    so this overlaps I/O with compute rather than running N encodes in true parallel."""
    if concurrency is None:
        concurrency = int(os.environ.get("POD_CONCURRENCY", "3"))
    concurrency = max(1, concurrency)
    clips = supa.fetch_clips(limit)
    print(f"claimed {len(clips)} clip(s) -> {len(clips)} videos (1 each) | concurrency={concurrency}")
    made = 0
    if concurrency == 1:
        for i, c in enumerate(clips):
            if _safe(i, c):
                made += 1
    else:
        # index is fixed per clip up-front so character/seed assignment stays deterministic
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [ex.submit(_safe, i, c) for i, c in enumerate(clips)]
            for fut in as_completed(futs):
                if fut.result():
                    made += 1
    print(f"\n==== DONE: {made}/{len(clips)} videos ====")
    return made

def main():
    ap = argparse.ArgumentParser(description="Render on-topic podcast clips into hooked PiP videos.")
    ap.add_argument("--limit", type=int, default=10, help="max clips to process (1 video each)")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="clips in flight at once (default POD_CONCURRENCY or 3)")
    ap.add_argument("--batch", default=None,
                    help="batch id stamped on each render row (default POD_BATCH)")
    a = ap.parse_args()
    if a.batch:
        global BATCH
        BATCH = a.batch
    run(a.limit, a.concurrency)

if __name__ == "__main__":
    main()
