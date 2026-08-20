#!/usr/bin/env python3
"""Render an explicit plan file (rows as produced by run_batch.plan()).
  python3 render_plan.py plan_repl.json [workers]
Resumable: rows whose output already exists are skipped."""
import os, sys, json, time, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[r for r in json.load(open(sys.argv[1])) if not os.path.exists(r["out"])]
W=int(sys.argv[2]) if len(sys.argv)>2 else 4
print(f"[render] {len(rows)} rows | {W} workers")
def one(r):
    t=time.time()
    cmd=[sys.executable, os.path.join(ROOT,"filler_mover.py"),
         "--base",r["clip"],"--manifest",r["manifest"],"--character",r["character"],
         "--placement",r["placement"],"--caption",r["caption"],
         "--caption-format",r["caption_format"],"--seed",str(r["seed"]),
         "--cut-h-frac","0.24","--out",r["out"]]
    cap=max(300, r["duration_s"]*8)
    try: p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap)
    except subprocess.TimeoutExpired:
        if os.path.exists(r["out"]): os.remove(r["out"])
        raise RuntimeError(f"{r['idx']}: runaway >{cap:.0f}s")
    if p.returncode!=0 or not os.path.exists(r["out"]):
        if os.path.exists(r["out"]): os.remove(r["out"])
        raise RuntimeError(f"{r['idx']}: {p.stderr.strip()[-250:]}")
    mb=os.path.getsize(r["out"])/1e6
    if mb > max(100, r["duration_s"]*3):
        os.remove(r["out"]); raise RuntimeError(f"{r['idx']}: runaway size {mb:.0f}MB")
    return r["idx"], mb, time.time()-t, ("skip-hook" if "[hook] skipped" in p.stdout else "")
done=fail=0
with ThreadPoolExecutor(max_workers=W) as ex:
    for f in as_completed([ex.submit(one,r) for r in rows]):
        try:
            i,mb,s,note=f.result(); done+=1
            print(f"  ok {i} ({mb:.0f}MB, {s:.0f}s) {note} [{done}/{len(rows)}]")
        except Exception as e:
            fail+=1; print(f"  FAIL {e}")
print(f"[render] done: {done} ok, {fail} failed")
