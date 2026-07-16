#!/usr/bin/env python3
"""
Re-render + upsert a SPECIFIC list of EA content rows in one of two audio modes,
without touching the DB rows (same bucket object name -> public URL unchanged).

  --mode laugh  : "Oh no no no" build intro (vo_begin_ohno) + low tail (vo_tail_ohno)
  --mode stock  : the stock cloned-voice VO (revert / default treatment)

  --ids  EA-041-V1,EA-041-V2,...     explicit comma list (required)

Idempotent, sequential, single-machine. Renders via stitch_embarrassed.py --local-only
(renders/test_<id>.mp4, no DB patch) then upserts <id>.mp4 into the embarrassed-angle bucket.
"""
import json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.expanduser("~/.config/peptide-secrets/.env")
for line in open(ENV_FILE):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SB_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"
SB_KEY = os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip('"').strip("'")
BUCKET = "embarrassed-angle"

def sb_get(path):
    req = urllib.request.Request(SB_URL + path, headers={
        "apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def upload(local_path, object_name):
    with open(local_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{SB_URL}/storage/v1/object/{BUCKET}/{object_name}",
        data=data, method="POST",
        headers={"apikey": SB_KEY, "Content-Type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=120).read()

def main():
    mode = sys.argv[sys.argv.index("--mode") + 1]
    ids = sys.argv[sys.argv.index("--ids") + 1].split(",")
    ids = [i.strip() for i in ids if i.strip()]
    assert mode in ("laugh", "stock")

    # map content_id -> row id
    rows = sb_get("/rest/v1/embarrassed_angle_content?select=id,content_id")
    by_name = {r["content_id"]: r["id"] for r in rows}

    env = dict(os.environ)
    if mode == "laugh":
        env["EMBARRASSED_VO_BEGIN"] = os.path.join(HERE, "assets", "vo_begin_ohno.wav")
        env["EMBARRASSED_VO_TAIL"]  = os.path.join(HERE, "assets", "vo_tail_ohno.wav")
        env["EMBARRASSED_VO_BUILD"] = "1"
    else:
        # stock: ensure no laugh env leaks in
        for k in ("EMBARRASSED_VO_BEGIN", "EMBARRASSED_VO_TAIL", "EMBARRASSED_VO_BUILD"):
            env.pop(k, None)

    print(f"mode={mode}  targets={len(ids)}", flush=True)
    ok = fail = 0
    for name in ids:
        rid = by_name.get(name)
        if rid is None:
            print(f"MISS {name}: no row"); fail += 1; continue
        try:
            subprocess.run(["/usr/bin/python3", os.path.join(HERE, "stitch_embarrassed.py"),
                            "--content_id", str(rid), "--local-only"],
                           env=env, check=True, capture_output=True, timeout=600)
            local = os.path.join(HERE, "renders", f"test_{name}.mp4")
            if not os.path.exists(local):
                raise RuntimeError("render output missing")
            upload(local, f"{name}.mp4")
            os.remove(local)
            ok += 1
            print(f"{mode.upper()} OK   {name}", flush=True)
        except Exception as e:
            fail += 1
            msg = (e.stderr or b"").decode()[-200:] if isinstance(e, subprocess.CalledProcessError) else str(e)
            print(f"{mode.upper()} FAIL {name}: {msg}", flush=True)
    print(f"DONE mode={mode}: {ok} ok, {fail} failed of {len(ids)}", flush=True)

if __name__ == "__main__":
    main()
