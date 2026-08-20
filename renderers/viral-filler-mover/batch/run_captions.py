#!/usr/bin/env python3
"""Fill posting captions for batch VFM-B1-0819 via the live n8n [Universal] Caption Maker.
Uses the workflow's POST-BAN-REMEDIATION defaults (no CTA, narrative voice, lifestyle
hashtags) — the repo's caption_config.json still carries the QUIZ CTA that the 2026-08-07
patch put on the baseline banned list, so passing it would reject every caption.
Chunked at 12/call: the n8n Code node has a 60s task cap."""
import json, time, urllib.request
URL="https://czed.app.n8n.cloud/webhook/caption-maker"
CFG={"source":{"table":"viral_filler_content",
               "filter":"batch=eq.VFM-B1-0819&caption=is.null&status=eq.done",
               "id_column":"id","limit":12,
               "context_columns":["hook","about","hook_angle","handle"]},
     "output":{"target_column":"caption","timestamp_column":"caption_generated_at"},
     "concurrency":10}
total=0
for i in range(12):
    req=urllib.request.Request(URL,data=json.dumps(CFG).encode(),
        headers={"Content-Type":"application/json"})
    t=time.time()
    try: r=json.load(urllib.request.urlopen(req,timeout=300))
    except Exception as e: print(f"  call {i+1} error: {e}"); break
    p=r.get("processed",0); total+=p
    print(f"  call {i+1}: processed {p} (fails {r.get('failures_total',0)}) {time.time()-t:.0f}s")
    if r.get("failures_sample"): print("     ", r["failures_sample"][:2])
    if p==0: break
print("captions written:",total)
