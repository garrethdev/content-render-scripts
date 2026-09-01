"""Orchestrator: pool -> per-clip pipeline -> Supabase. One video per clip.

Per clip: download -> analyze (manifest) -> detect existing text -> (hook or hide) -> render -> upload -> record.
If the clip already has a burned-in hook, ours is hidden; otherwise one Claude hook is burned. Idempotent.
"""
import os, argparse
from . import config, supa, media, hookscan, hooks

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
    supa.insert_render({"clip_video_id": vid, "show": clip["show"], "host": clip["host"],
                        "hook": hook_used, "variant": 1, "character": character,
                        "seed": seed, "render_url": url, "status": "done"})
    supa.patch_clip(vid, {"status": "staged", "has_onscreen_top_text": has_text})
    print(f"   char={character} our_hook={'no' if has_text else 'yes'} -> {url}")
    return url

def run(limit):
    clips = supa.fetch_clips(limit)
    print(f"claimed {len(clips)} clip(s) -> {len(clips)} videos (1 each)")
    made = 0
    for i, c in enumerate(clips):
        try:
            if process_clip(i, c):
                made += 1
        except Exception as e:               # one bad clip must never kill the batch
            print(f"   [{i+1}] SKIPPED after error: {type(e).__name__}: {e}")
    print(f"\n==== DONE: {made}/{len(clips)} videos ====")
    return made

def main():
    ap = argparse.ArgumentParser(description="Render on-topic podcast clips into hooked PiP videos.")
    ap.add_argument("--limit", type=int, default=10, help="max clips to process (1 video each)")
    run(ap.parse_args().limit)

if __name__ == "__main__":
    main()
