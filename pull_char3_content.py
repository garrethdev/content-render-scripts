#!/usr/bin/env python3
"""Pull finished Character 3 video content from Supabase (both lanes) for review/posting.

Lanes:
  jealousy  -> jealousy_char3_content  (JEL-###, quote treadmill BA)   approved = quality_status='top30'
  mito      -> mito_hooks              (metabolic weightlifting montage) approved = gate_status='approved'

Downloads each finished row's final_video into ./char3_out/<lane>/<id>.mp4 and writes
one manifest.csv (lane, id, on-screen text, suggested_ig_music, caption, final_video).

Usage:
  python pull_char3_content.py                 # both lanes: videos + manifest
  python pull_char3_content.py --lane jealousy # one lane only (jealousy | mito | all)
  python pull_char3_content.py --manifest      # manifest.csv only, no downloads
  python pull_char3_content.py --ready         # only scheduler_ready=true rows (released set)

Env: CAROUSEL_SUPABASE_SECRET_KEY  (run `peptide-env`, or source ~/.config/peptide-secrets/.env)
"""
import csv, json, os, sys, urllib.request, urllib.parse

SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
if not KEY:
    sys.exit("Set CAROUSEL_SUPABASE_SECRET_KEY (run `peptide-env` or source ~/.config/peptide-secrets/.env)")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "char3_out")

# lane -> (table, id_col, text_cols, approved_filter)
LANES = {
    "jealousy": ("jealousy_char3_content", "carousel_id",
                 ["text_hook", "text_hook_after"], "quality_status=eq.top30"),
    "mito":     ("mito_hooks", "hook_id",
                 ["hook_text", "beat1", "beat2", "beat3"], "gate_status=eq.approved"),
}


def rest(path):
    req = urllib.request.Request(SB + "/rest/v1/" + path, headers=H)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def pull(lane, writer, manifest_only, ready_only):
    table, idc, tcols, approved = LANES[lane]
    sel = ",".join([idc, "suggested_ig_music", "caption", "final_video"] + tcols)
    flt = f"{approved}&used=eq.true&final_video=not.is.null"
    if ready_only:
        flt += "&scheduler_ready=eq.true"
    rows = rest(f"{table}?{flt}&select={sel}&order={idc}")
    print(f"[{lane}] {len(rows)} rows")
    d = os.path.join(OUT, lane)
    os.makedirs(d, exist_ok=True)
    for r in rows:
        rid = r[idc]
        text = " | ".join((r.get(c) or "").replace("\n", " ") for c in tcols)
        if not manifest_only and r.get("final_video"):
            dst = os.path.join(d, f"{rid}.mp4")
            try:
                urllib.request.urlretrieve(r["final_video"], dst)
                print(f"  OK  {rid}")
            except Exception as e:
                print(f"  FAIL {rid}: {str(e)[:100]}")
        writer.writerow([lane, rid, text, r.get("suggested_ig_music") or "",
                         (r.get("caption") or "").replace("\n", "\\n"), r.get("final_video") or ""])


def main():
    args = sys.argv[1:]
    manifest_only = "--manifest" in args
    ready_only = "--ready" in args
    lane = "all"
    if "--lane" in args:
        lane = args[args.index("--lane") + 1]
    lanes = list(LANES) if lane == "all" else [lane]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "manifest.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lane", "id", "text", "suggested_ig_music", "caption", "final_video"])
        for ln in lanes:
            pull(ln, w, manifest_only, ready_only)
    print(f"manifest -> {os.path.join(OUT, 'manifest.csv')}")
    if not manifest_only:
        print(f"videos   -> {OUT}/<lane>/")


if __name__ == "__main__":
    main()
