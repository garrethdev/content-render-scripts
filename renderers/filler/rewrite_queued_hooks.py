#!/usr/bin/env python3
"""Rewrite the hooks on still-queued jobs using the matcher's current model (GLM-4.6).
Race-safe: only updates rows still in status='queued' (won't touch ones already rendering/done)."""
from collections import defaultdict
import supa
from queue_match import gen_hooks   # uses whatever model queue_match is set to

rows = supa.rest("viral_filler_content?status=eq.queued&select=id,filler_aweme_id,about,hook_angle&order=id") or []
by_clip = defaultdict(list)
for r in rows:
    by_clip[r["filler_aweme_id"]].append(r)

updated = 0
for aweme, rs in by_clip.items():
    rs = sorted(rs, key=lambda x: x["id"])
    hooks = gen_hooks(rs[0].get("about"), rs[0].get("hook_angle"))
    for i, r in enumerate(rs):
        supa.rest(f"viral_filler_content?id=eq.{r['id']}&status=eq.queued", "PATCH",
                  {"hook": hooks[i % len(hooks)]}, prefer="return=minimal")
        updated += 1
print(f"rewrote hooks on {updated} queued rows across {len(by_clip)} clips with GLM-4.6")
