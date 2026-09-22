#!/usr/bin/env python3
"""Turn the three batch5 part files into cleora_content rows."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch5_part1, batch5_part2, batch5_part3

order = [l.strip() for l in open(os.path.join(HERE, '..', 'longlist', 'picks.txt'))
         if l.strip()]
S = {}
for m in (batch5_part1, batch5_part2, batch5_part3):
    S.update(m.S)

missing = [i for i in order if i not in S]
if missing:
    sys.exit("no script written for: " + ", ".join(missing))

def story_key(t):
    return re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')[:40]

rows = []
for n, pick in enumerate(order, 1):
    v = S[pick]
    beats = [{"vo": vo, "kind": kind, "slot": slot, "caption": cap}
             for (vo, kind, slot, cap) in v["beats"]]
    words = sum(len(b["vo"].split()) for b in beats)
    rows.append({
        "content_id": f"CLE-B5-{n:04d}",
        "batch_id": "cleora-b5",
        "story_key": story_key(v["title"]),
        "title": v["title"],
        # The opening card is its own line, NOT a copy of beats[0].vo - that
        # duplication is the defect on the existing 25 approved rows.
        "hook_text": v["card"],
        "script": {"beats": beats, "words": words,
                   "source": "writing-agent v3 (Shalev shape; Director assigns clips)",
                   "subject_gender": "female"},
        "script_status": "written",
        "notes": f"batch 5, owner-picked from the long list ({pick})",
    })

out = os.path.join(HERE, 'batch5_rows.json')
json.dump(rows, open(out, 'w'), indent=1)
print(f"{len(rows)} rows -> {out}")
for r in rows:
    dup = r["hook_text"].strip() == r["script"]["beats"][0]["vo"].strip()
    print(f"  {r['content_id']}  {r['script']['words']:3}w  "
          f"{'CARD==VO !!' if dup else 'card distinct'}  {r['title']}")
