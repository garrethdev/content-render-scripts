#!/usr/bin/env python3
"""
Batch driver for the Viral Filler MOVING-CUTOUT format (v0.0.1).

Batch VFM-B1-0819: 50 bases x 2 variants = 100 videos.
  download -> probe (once per base) -> render 2 variants -> log

Each stage is resumable: existing outputs are skipped, so a crash or a
Ctrl-C only costs the in-flight item.

  python3 run_batch.py download
  python3 run_batch.py probe   [workers]
  python3 run_batch.py render  [workers]
  python3 run_batch.py status
"""
import os, sys, json, time, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
CLIPS  = os.path.join(HERE, "clips");     os.makedirs(CLIPS, exist_ok=True)
MANIF  = os.path.join(HERE, "manifests"); os.makedirs(MANIF, exist_ok=True)
OUT    = os.path.join(HERE, "renders");   os.makedirs(OUT, exist_ok=True)

BATCH_ID    = "VFM-B1-0819"
CHARS       = ["char2", "char3", "char4"]
PLACEMENTS  = ["roam_bottom", "roam_right", "roam_left", "roam_free"]
FORMATS     = ["outline", "black_box", "white_box"]
CUT_H_FRAC  = 0.24          # standing decision: 20% smaller than the 0.30 default
PIP_H_FRAC  = 0.24          # probe must match the render footprint
HOOK_DUR    = 2.6

bases = json.load(open(os.path.join(HERE, "bases.json")))
hooks = json.load(open(os.path.join(HERE, "hooks.json")))


def plan():
    """The full 100-row render plan. Deterministic — same plan every run."""
    rows = []
    used = set()          # captions already spoken for, so no two videos share a hook
    for i, b in enumerate(bases):
        aid = str(b["aweme_id"])
        hs = hooks.get(aid, [])
        for v in (0, 1):
            cap = next((h for h in hs[v:] + hs if h not in used), hs[v] if len(hs) > v else "")
            used.add(cap)
            rows.append({
                "batch_id": BATCH_ID,
                "idx": i * 2 + v,
                "aweme_id": aid, "handle": b["handle"], "duration_s": b["duration_s"],
                "hook_angle": b["hook_angle"], "theme": b["theme"],
                "character": CHARS[(i + v) % 3],
                "placement": PLACEMENTS[(i * 2 + v) % 4],
                "caption_format": FORMATS[(i * 2 + v) % 3],
                "caption": cap,
                "seed": 1000 + i * 10 + v,
                "clip": os.path.join(CLIPS, f"{aid}.mp4"),
                "manifest": os.path.join(MANIF, f"{aid}.manifest.json"),
                "out": os.path.join(OUT, f"{BATCH_ID}_{i*2+v:03d}_{aid}_{CHARS[(i+v)%3]}.mp4"),
            })
    return rows


def download():
    todo = [b for b in bases if not os.path.exists(os.path.join(CLIPS, f"{b['aweme_id']}.mp4"))]
    print(f"[download] {len(todo)} to fetch, {len(bases)-len(todo)} cached")
    def one(b):
        dst = os.path.join(CLIPS, f"{b['aweme_id']}.mp4"); tmp = dst + ".part"
        urllib.request.urlretrieve(b["source_video_url"], tmp)
        os.replace(tmp, dst)
        return b["aweme_id"], os.path.getsize(dst) / 1e6
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(one, b) for b in todo]):
            try:
                aid, mb = f.result(); ok += 1
                print(f"  ok {aid} ({mb:.1f} MB)  [{ok}/{len(todo)}]")
            except Exception as e:
                fail += 1; print(f"  FAIL {e}")
    print(f"[download] done: {ok} ok, {fail} failed")


def probe(workers=6):
    todo = [b for b in bases
            if os.path.exists(os.path.join(CLIPS, f"{b['aweme_id']}.mp4"))
            and not os.path.exists(os.path.join(MANIF, f"{b['aweme_id']}.manifest.json"))]
    print(f"[probe] {len(todo)} to probe, {len(bases)-len(todo)} cached | {workers} workers")
    def one(b):
        aid = str(b["aweme_id"]); t = time.time()
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "probe_base.py"),
             os.path.join(CLIPS, f"{aid}.mp4"),
             os.path.join(MANIF, f"{aid}.manifest.json"), str(PIP_H_FRAC), str(HOOK_DUR)],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"{aid}: {r.stderr.strip()[-300:]}")
        return aid, time.time() - t
    done = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, b) for b in todo]):
            try:
                aid, secs = f.result(); done += 1
                print(f"  ok {aid} ({secs:.0f}s)  [{done}/{len(todo)}]")
            except Exception as e:
                fail += 1; print(f"  FAIL {e}")
    print(f"[probe] done: {done} ok, {fail} failed")


def render(workers=4):
    rows = [r for r in plan()
            if os.path.exists(r["manifest"]) and not os.path.exists(r["out"])]
    print(f"[render] {len(rows)} to render | {workers} workers")
    def one(r):
        t = time.time()
        cmd = [sys.executable, os.path.join(ROOT, "filler_mover.py"),
               "--base", r["clip"], "--manifest", r["manifest"],
               "--character", r["character"], "--placement", r["placement"],
               "--caption", r["caption"], "--caption-format", r["caption_format"],
               "--seed", str(r["seed"]), "--cut-h-frac", str(CUT_H_FRAC),
               "--out", r["out"]]
        # guard: a render that outruns 8x realtime is hung -> kill and drop the partial
        cap = max(300, r["duration_s"] * 8)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=cap)
        except subprocess.TimeoutExpired:
            if os.path.exists(r["out"]): os.remove(r["out"])
            raise RuntimeError(f"idx {r['idx']} {r['aweme_id']}: runaway (> {cap:.0f}s), killed")
        if p.returncode != 0 or not os.path.exists(r["out"]):
            if os.path.exists(r["out"]): os.remove(r["out"])
            raise RuntimeError(f"idx {r['idx']} {r['aweme_id']}: {p.stderr.strip()[-300:]}")
        mb = os.path.getsize(r["out"]) / 1e6
        if mb > max(100, r["duration_s"] * 3):
            os.remove(r["out"]); raise RuntimeError(f"idx {r['idx']}: runaway size {mb:.0f}MB")
        return r["idx"], mb, time.time() - t
    done = fail = 0; fails = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, r) for r in rows]):
            try:
                idx, mb, secs = f.result(); done += 1
                print(f"  ok {idx:03d} ({mb:.0f}MB, {secs:.0f}s)  [{done}/{len(rows)}]")
            except Exception as e:
                fail += 1; fails.append(str(e)); print(f"  FAIL {e}")
    print(f"[render] done: {done} ok, {fail} failed")
    if fails: print("\n".join("  " + f for f in fails))


def status():
    rows = plan()
    nc = sum(1 for b in bases if os.path.exists(os.path.join(CLIPS, f"{b['aweme_id']}.mp4")))
    nm = sum(1 for b in bases if os.path.exists(os.path.join(MANIF, f"{b['aweme_id']}.manifest.json")))
    nr = sum(1 for r in rows if os.path.exists(r["out"]))
    print(f"batch {BATCH_ID}: clips {nc}/{len(bases)} | manifests {nm}/{len(bases)} | renders {nr}/{len(rows)}")
    json.dump(rows, open(os.path.join(HERE, "plan.json"), "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    {"download": lambda: download(),
     "probe":    lambda: probe(arg or 6),
     "render":   lambda: render(arg or 4),
     "status":   lambda: status()}[cmd]()
