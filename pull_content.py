#!/usr/bin/env python3
"""Unified pull + prep-audit for the Char2/Char3 posting pool (target: 101 pieces).

Lanes (all land in the Smart Scheduler pool once released):
  char3_jealousy   jealousy_char3_content   30  quote treadmill BA   (approved = quality_status='top30')
  char3_mito       mito_hooks               41  metabolic montage    (approved = gate_status='approved')
  char2_slideshow  ba_2slide_content        30  2-slide before/after (Character 2; scope with --char2-batch)

Two jobs:
  1. PULL  — download each lane's finished videos into content_out/<lane>/ + one manifest.csv
  2. AUDIT — check every row against the scheduler-ready checklist and report what's missing,
             so you can see the 101 is genuinely prepped before release.

The scheduler picks a row up only when ALL of these hold (per the Smart Scheduler handover):
  scheduler_ready=true, gatekeep_status='approved', quality_status != 'poor',
  character set, final_video set, caption set, suggested_ig_music resolves in music_library,
  and posting_status / profile / scheduling columns are NULL.

Usage:
  python pull_content.py --audit                 # prep report for all lanes (no downloads)
  python pull_content.py --audit --char2-batch B # scope char2 to batch B
  python pull_content.py                          # download all finished videos + manifest
  python pull_content.py --manifest               # manifest.csv only
  python pull_content.py --lane char3_mito        # one lane
  python pull_content.py --ready                  # only released (scheduler_ready=true) rows

Env: CAROUSEL_SUPABASE_SECRET_KEY  (run `peptide-env`, or source ~/.config/peptide-secrets/.env)
"""
import csv, json, os, sys, urllib.request

SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
if not KEY:
    sys.exit("Set CAROUSEL_SUPABASE_SECRET_KEY (run `peptide-env` or source ~/.config/peptide-secrets/.env)")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content_out")

# lane -> table, id col, text cols, character value, approved filter
LANES = {
    "char3_jealousy": dict(table="jealousy_char3_content", idc="carousel_id",
                           tcols=["text_hook", "text_hook_after"], persona="Character 3",
                           approved="quality_status=eq.top30"),
    "char3_mito":     dict(table="mito_hooks", idc="hook_id",
                           tcols=["hook_text", "beat1", "beat2", "beat3"], persona="Character 3",
                           approved="gate_status=eq.approved"),
    "char2_slideshow": dict(table="ba_2slide_content", idc="carousel_id",
                            tcols=["text_hook", "text_hook_after"], persona="Character 2",
                            approved="character=eq.Character 2"),
}


def rest(path):
    req = urllib.request.Request(SB + "/rest/v1/" + urllib.parse.quote(path, safe="/?&=*.,()'"),
                                 headers=H)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


import urllib.parse

# music_library lookup, cached
_ML = None
def music_ok(val):
    global _ML
    if not val:
        return False
    if _ML is None:
        rows = rest("music_library?select=artist,title")
        _ML = {f"{r['artist']} - {r['title']}" for r in rows}
    return val in _ML


def rows_for(lane, char2_batch, ready_only):
    c = LANES[lane]
    cols = list({c["idc"], "character", "caption", "final_video", "suggested_ig_music",
                 "scheduler_ready", "gatekeep_status", "quality_status", "posting_status",
                 *c["tcols"]})
    flt = c["approved"] + "&used=eq.true" if lane != "char2_slideshow" else c["approved"]
    if lane == "char2_slideshow" and char2_batch:
        flt += f"&batch=eq.{char2_batch}"
    if ready_only:
        flt += "&scheduler_ready=eq.true"
    return c, rest(f"{c['table']}?{flt}&select={','.join(cols)}&order={c['idc']}")


def audit_row(lane, c, r):
    miss = []
    if not r.get("final_video"): miss.append("no video")
    if not r.get("caption"): miss.append("no caption")
    if not music_ok(r.get("suggested_ig_music")): miss.append("music unresolved")
    if r.get("character") != c["persona"]: miss.append("persona")
    if r.get("gatekeep_status") != "approved": miss.append("not approved")
    if (r.get("quality_status") or "") == "poor": miss.append("quality poor")
    if r.get("posting_status") is not None: miss.append("already scheduled")
    return miss


def do_audit(char2_batch):
    grand = 0
    print("== PREP AUDIT ==")
    for lane in LANES:
        c, rows = rows_for(lane, char2_batch, ready_only=False)
        ready = sum(1 for r in rows if not audit_row(lane, c, r))
        released = sum(1 for r in rows if r.get("scheduler_ready"))
        grand += ready
        print(f"\n[{lane}]  rows={len(rows)}  prepped={ready}  released={released}")
        # show the blockers
        from collections import Counter
        blockers = Counter()
        for r in rows:
            for m in audit_row(lane, c, r):
                blockers[m] += 1
        for m, n in blockers.most_common():
            print(f"    - {n} × {m}")
    print(f"\nTOTAL prepped and postable (pending scheduler_ready flip): {grand} / 101")


def do_pull(lane_filter, manifest_only, ready_only, char2_batch):
    os.makedirs(OUT, exist_ok=True)
    lanes = list(LANES) if lane_filter == "all" else [lane_filter]
    with open(os.path.join(OUT, "manifest.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lane", "id", "character", "text", "suggested_ig_music",
                    "music_resolves", "caption", "final_video"])
        for lane in lanes:
            c, rows = rows_for(lane, char2_batch, ready_only)
            print(f"[{lane}] {len(rows)} rows")
            d = os.path.join(OUT, lane); os.makedirs(d, exist_ok=True)
            for r in rows:
                rid = r[c["idc"]]
                text = " | ".join((r.get(t) or "").replace("\n", " ") for t in c["tcols"])
                if not manifest_only and r.get("final_video"):
                    try:
                        urllib.request.urlretrieve(r["final_video"], os.path.join(d, f"{rid}.mp4"))
                        print(f"  OK  {rid}")
                    except Exception as e:
                        print(f"  FAIL {rid}: {str(e)[:100]}")
                w.writerow([lane, rid, r.get("character") or "", text,
                            r.get("suggested_ig_music") or "", music_ok(r.get("suggested_ig_music")),
                            (r.get("caption") or "").replace("\n", "\\n"), r.get("final_video") or ""])
    print(f"manifest -> {os.path.join(OUT, 'manifest.csv')}")
    if not manifest_only:
        print(f"videos   -> {OUT}/<lane>/")


def main():
    a = sys.argv[1:]
    char2_batch = a[a.index("--char2-batch") + 1] if "--char2-batch" in a else None
    if "--audit" in a:
        do_audit(char2_batch); return
    lane = a[a.index("--lane") + 1] if "--lane" in a else "all"
    do_pull(lane, "--manifest" in a, "--ready" in a, char2_batch)


if __name__ == "__main__":
    main()
