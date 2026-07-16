#!/usr/bin/env python3
"""Render the entire queue, then exit. Run several copies in parallel for throughput —
the optimistic claim (PATCH ... where status='queued') keeps two workers off the same job.
"""
import worker, render, time

rendered = 0
while True:
    try:
        if worker.queue_depth() == 0:
            break
        d, f = worker.run_batch(fire_captions=False)
        rendered += d
    except Exception as e:                       # transient API/network hiccup -> retry, never crash
        print("[drain] transient error, retrying in 5s:", str(e)[:140])
        time.sleep(5)
try:
    render.trigger_captions()
except Exception:
    pass
print(f"[drain] rendered {rendered}")
