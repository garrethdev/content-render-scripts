"""
Dating Reaction — end-to-end orchestrator (library-aware).

Give it a library row id (or explicit source) plus the shared reaction + cutout,
and it renders the finished video: caption check -> face/text timeline -> PiP
motion (corner-hop, hook-aware) -> render (moving cutout over the FULL source
with the HOOK burned on top for the first ~1.8s, then hard cut to the reaction
full-screen). Uses the FULL source clip (project rule).

Usage (by library row):
  python3 run_pipeline.py --row-id 3 --reaction REACT.mp4 --cutout CUTOUT.webm \
      --out OUT.mp4 [--supabase-key sb_secret_...] [--hook-dur 1.8]

Usage (explicit source, no DB):
  python3 run_pipeline.py --source SRC.mp4 --hook "..." --transcript "..." \
      --reaction REACT.mp4 --cutout CUTOUT.webm --out OUT.mp4

Row mode reads video_public_url + text_hook_content + transcript from
public.dating_reaction_sources (project qlcmgxgwpzmiebzxflai). Supabase key from
--supabase-key or the SUPABASE_KEY env var.
"""
import argparse, os, sys, json, subprocess, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SB_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + "\n" + r.stderr + "\n")
        raise SystemExit(f"step failed: {' '.join(str(a) for a in args[:3])}...")
    return r.stdout


def fetch_row(row_id, key):
    url = (f"{SB_URL}/rest/v1/dating_reaction_sources?id=eq.{row_id}"
           "&select=video_public_url,text_hook_content,transcript")
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read())
    if not rows:
        raise SystemExit(f"row {row_id} not found")
    return rows[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row-id")
    ap.add_argument("--source")
    ap.add_argument("--hook", default="")
    ap.add_argument("--transcript", default="")
    ap.add_argument("--reaction", required=True)
    ap.add_argument("--cutout", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY", ""))
    ap.add_argument("--hook-dur", default="1.8")
    ap.add_argument("--analyze-fps", default="6")
    ap.add_argument("--reaction-trim", default="3.6")
    ap.add_argument("--reaction-dur", default="14.7")
    a = ap.parse_args()

    work = tempfile.mkdtemp()
    src, hook, transcript = a.source, a.hook, a.transcript

    if a.row_id:
        if not a.supabase_key:
            raise SystemExit("row mode needs --supabase-key or SUPABASE_KEY env")
        row = fetch_row(a.row_id, a.supabase_key)
        src = src or row.get("video_public_url")
        hook = hook or (row.get("text_hook_content") or "")
        transcript = transcript or (row.get("transcript") or "")
        print(f"ROW {a.row_id}: hook={hook[:60]!r}")

    if not src:
        raise SystemExit("need --source or --row-id")
    if src.startswith("http"):
        local = os.path.join(work, "source.mp4")
        urllib.request.urlretrieve(src, local)
        src = local

    cap = sh([PY, os.path.join(HERE, "caption_detect.py"), src, "--transcript", transcript, "--json"])
    print("CAPTIONS:", cap.strip())
    try:
        has_captions = bool(json.loads(cap).get("has_captions"))
    except Exception:
        has_captions = False

    # RULE: only add our hook when the source has NO on-screen text of its own.
    # If the source already shows captions, skip the hook (and let the PiP use the
    # top, so don't reserve the hook band either).
    if has_captions and hook:
        print("Source already has captions -> SKIPPING hook overlay")
        hook = ""
    # ALWAYS reserve the hook band for the solver: hooks are burned in a separate
    # post-pass (local ffmpeg has no drawtext), so even with hook=="" here a hook
    # will sit top-center for the first seconds of the final video.
    hook_dur = a.hook_dur

    tl = os.path.join(work, "timeline.json")
    print(sh([PY, os.path.join(HERE, "analyze_timeline.py"), src, tl, a.analyze_fps]).strip())

    mo = os.path.join(work, "motion.json")
    # hook-aware: pass HOOK_DUR so the PiP avoids the top band while the hook shows
    print(sh([PY, os.path.join(HERE, "motion_solver.py"), tl, mo,
              "0.424", "0.317", "0.025", "0.5", hook_dur, "0.20"]).strip())

    print(sh([PY, os.path.join(HERE, "render_dating_reaction.py"),
              src, a.cutout, a.reaction, mo, a.out,
              a.reaction_trim, a.reaction_dur, hook, hook_dur]).strip())
    print("FINAL:", a.out, "| hook:", "yes" if hook else "no (source had text)")


if __name__ == "__main__":
    main()
