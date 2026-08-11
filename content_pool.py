#!/usr/bin/env python3
"""content_pool.py — Content-pool EXPORT + scheduler-readiness AUDIT for the
Char2/Char3 posting lanes. This is an OPS/QA tool, not a renderer: it reads the
finished content lanes out of Supabase, downloads their media, and reports which
rows are genuinely postable before you release them to the Smart Scheduler.

Lanes (all feed the Smart Scheduler pool once released):
  char3_jealousy   jealousy_char3_content   30  quote treadmill BA (video)   approved=quality_status='top30'
  char3_mito       mito_hooks               41  metabolic montage  (video)   approved=gate_status='approved'
  char2_slideshow  char2_slideshow          30  image slideshow (1-12 slides) approved=new unpublished rows

Two jobs:
  1. PULL  — download each lane's finished media into content_out/<lane>/ + one manifest.csv
             (video lanes -> <id>.mp4 ; slideshow -> <id>/slide_N.jpg)
  2. AUDIT — check every row against the scheduler-ready checklist and report blockers,
             so you can confirm the pool is genuinely prepped before release.

Scheduler picks a row up only when: scheduler_ready=true, gatekeep_status='approved',
quality_status != 'poor', character set, media present, caption set, music resolves in
music_library, and posting_status / profile / scheduling columns are NULL.

Usage:
  python content_pool.py --audit                       # prep report, all lanes
  python content_pool.py --audit --char2-batch B       # scope char2 to batch B
  python content_pool.py                                # download all finished media + manifest
  python content_pool.py --manifest                    # manifest.csv only
  python content_pool.py --lane char3_mito             # one lane
  python content_pool.py --ready                        # only released (scheduler_ready=true)

Secrets: read via common/env.py — from ~/.config/peptide-secrets/.env or a
git-ignored <repo-root>/.env (see .env.example). NEVER hardcode the key here.
Override ad hoc with --key <SUPABASE_SECRET_KEY> when running off-machine.
"""
import csv, json, os, sys, urllib.request, urllib.parse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env  # noqa: E402

SB = env.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = (sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv
       else env.get("CAROUSEL_SUPABASE_SECRET_KEY") or env.get("SUPABASE_SERVICE_KEY"))
if not KEY:
    sys.exit("No Supabase key. Set CAROUSEL_SUPABASE_SECRET_KEY in "
             "~/.config/peptide-secrets/.env or <repo>/.env, or pass --key <KEY>.")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}
OUT = os.path.join(os.getcwd(), "content_out")
SLIDES = [f"slide_{i}_url" for i in range(1, 13)]

LANES = {
    "char3_jealousy": dict(table="jealousy_char3_content", idc="carousel_id", persona="Character 3",
                           tcols=["text_hook", "text_hook_after"], music="suggested_ig_music",
                           media="final_video", approved="quality_status=eq.top30&used=eq.true"),
    "char3_mito":     dict(table="mito_hooks", idc="hook_id", persona="Character 3",
                           tcols=["hook_text", "beat1", "beat2", "beat3"], music="suggested_ig_music",
                           media="final_video", approved="gate_status=eq.approved&used=eq.true"),
    "char2_slideshow": dict(table="char2_slideshow", idc="carousel_id", persona="Character 2",
                            tcols=["angle"], music="music", media="slides",
                            approved="posting_status=is.null&slide_1_url=not.is.null"),
}


def rest(path):
    req = urllib.request.Request(SB + "/rest/v1/" + path, headers=H)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


_ML = None
def music_ok(val):
    global _ML
    if not val:
        return False
    if _ML is None:
        _ML = {f"{r['artist']} - {r['title']}" for r in rest("music_library?select=artist,title")}
    return val in _ML


def rows_for(lane, char2_batch, ready_only):
    c = LANES[lane]
    media_cols = SLIDES if c["media"] == "slides" else [c["media"]]
    cols = list({c["idc"], "character", "caption", c["music"], "scheduler_ready",
                 "gatekeep_status", "quality_status", "posting_status", *c["tcols"], *media_cols})
    flt = c["approved"]
    if lane == "char2_slideshow" and char2_batch:
        flt += f"&batch=eq.{char2_batch}"
    if ready_only:
        flt += "&scheduler_ready=eq.true"
    return c, rest(f"{c['table']}?{urllib.parse.quote(flt, safe='=&.*')}&select={','.join(cols)}&order={c['idc']}")


def media_urls(c, r):
    if c["media"] == "slides":
        return [r[k] for k in SLIDES if r.get(k)]
    return [r[c["media"]]] if r.get(c["media"]) else []


def audit_row(c, r):
    miss = []
    if not media_urls(c, r): miss.append("no media")
    if not (r.get("caption") or "").strip(): miss.append("no caption")
    if not music_ok(r.get(c["music"])): miss.append("music unresolved")
    if r.get("character") != c["persona"]: miss.append("persona")
    if r.get("gatekeep_status") != "approved": miss.append("not approved")
    if (r.get("quality_status") or "") == "poor": miss.append("quality poor")
    if r.get("posting_status") is not None: miss.append("already scheduled")
    return miss


def do_audit(char2_batch):
    grand = 0
    print("== PREP AUDIT ==")
    for lane in LANES:
        c, rows = rows_for(lane, char2_batch, False)
        ready = sum(1 for r in rows if not audit_row(c, r))
        released = sum(1 for r in rows if r.get("scheduler_ready"))
        grand += ready
        print(f"\n[{lane}]  rows={len(rows)}  prepped={ready}  released={released}")
        blk = Counter(m for r in rows for m in audit_row(c, r))
        for m, n in blk.most_common():
            print(f"    - {n} x {m}")
    print(f"\nTOTAL prepped and postable (pending scheduler_ready flip): {grand} / 101")


def do_pull(lane_filter, manifest_only, ready_only, char2_batch):
    os.makedirs(OUT, exist_ok=True)
    lanes = list(LANES) if lane_filter == "all" else [lane_filter]
    with open(os.path.join(OUT, "manifest.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lane", "id", "character", "text", "music", "music_resolves", "caption", "media"])
        for lane in lanes:
            c, rows = rows_for(lane, char2_batch, ready_only)
            print(f"[{lane}] {len(rows)} rows")
            d = os.path.join(OUT, lane); os.makedirs(d, exist_ok=True)
            for r in rows:
                rid = r[c["idc"]]; urls = media_urls(c, r)
                if not manifest_only and urls:
                    try:
                        if c["media"] == "slides":
                            sd = os.path.join(d, rid); os.makedirs(sd, exist_ok=True)
                            for n, u in enumerate(urls, 1):
                                ext = os.path.splitext(u.split("?")[0])[1] or ".jpg"
                                urllib.request.urlretrieve(u, os.path.join(sd, f"slide_{n}{ext}"))
                        else:
                            urllib.request.urlretrieve(urls[0], os.path.join(d, f"{rid}.mp4"))
                        print(f"  OK  {rid}")
                    except Exception as e:
                        print(f"  FAIL {rid}: {str(e)[:100]}")
                text = " | ".join((r.get(t) or "").replace("\n", " ") for t in c["tcols"])
                w.writerow([lane, rid, r.get("character") or "", text, r.get(c["music"]) or "",
                            music_ok(r.get(c["music"])), (r.get("caption") or "").replace("\n", "\\n"),
                            " ; ".join(urls)])
    print(f"manifest -> {os.path.join(OUT, 'manifest.csv')}")
    if not manifest_only:
        print(f"media    -> {OUT}/<lane>/")


def main():
    a = sys.argv[1:]
    char2_batch = a[a.index("--char2-batch") + 1] if "--char2-batch" in a else None
    if "--audit" in a:
        do_audit(char2_batch); return
    lane = a[a.index("--lane") + 1] if "--lane" in a else "all"
    do_pull(lane, "--manifest" in a, "--ready" in a, char2_batch)


if __name__ == "__main__":
    main()
