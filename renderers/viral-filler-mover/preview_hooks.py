#!/usr/bin/env python3
"""Dry-run hook preview: generate + store a proposed hook (from title) for the next N on-topic clean clips,
WITHOUT rendering. Lets the user review copy before the expensive render. The worker reuses proposed_hook
(no regeneration). Usage: python3 preview_hooks.py [N]
"""
import sys, json, random
from podcast_lane import supa, hooks, config

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    clips = supa.fetch_clips(n)                     # capped per-show selection (no show dominates)
    rng = random.Random(7)
    styles = (hooks.STYLE_MIX * (len(clips) // len(hooks.STYLE_MIX) + 1))[:len(clips)]
    rng.shuffle(styles)
    print(f"{'#':>2}  {'STYLE':9} {'SHOW':22} HOOK")
    print("-" * 100)
    for i, (c, style) in enumerate(zip(clips, styles), 1):
        if c.get("proposed_hook"):                 # keep already-approved hooks; only fill new clips
            hook = c["proposed_hook"]
        else:
            emoji = (i % 3 == 0)
            hook = hooks.gen_hook(c.get("title", ""), c.get("show", ""), emoji=emoji, style=style)
            supa.patch_clip(c["video_id"], {"proposed_hook": hook})
        print(f"{i:>2}  {style:9} {c['show'][:22]:22} {hook}")

if __name__ == "__main__":
    main()
