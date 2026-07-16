#!/usr/bin/env bash
# Pull all rendered Embarrassed Content Angle videos + their metadata.
# Public bucket — no auth needed. Usage: bash pull_embarrassed.sh [outdir]
set -euo pipefail

# load secrets from the machine-local env (never hardcode the key)
[ -f "$HOME/.config/peptide-secrets/.env" ] && set -a && . "$HOME/.config/peptide-secrets/.env" && set +a
SB="${SUPABASE_URL:-https://qlcmgxgwpzmiebzxflai.supabase.co}"
ANON="${SUPABASE_ANON_KEY:?set SUPABASE_ANON_KEY in ~/.config/peptide-secrets/.env or the environment}"
OUT="${1:-embarrassed_videos}"
mkdir -p "$OUT"

# 1) pull the manifest (content_id, hook, caption, url) for every rendered row
curl -s "$SB/rest/v1/embarrassed_angle_content?stitch_status=eq.rendered&select=content_id,text_hook,caption,video_public_url,posting_status&order=content_id" \
  -H "apikey: $ANON" -H "Authorization: Bearer $ANON" > "$OUT/manifest.json"

# 2) extract URLs and download each mp4 (named <content_id>.mp4)
python3 - "$OUT" <<'PY'
import json, os, sys, urllib.request
out = sys.argv[1]
rows = json.load(open(f"{out}/manifest.json"))
print(f"{len(rows)} rendered videos")
for r in rows:
    url, cid = r["video_public_url"], r["content_id"]
    dst = os.path.join(out, f"{cid}.mp4")
    if os.path.exists(dst):
        continue
    try:
        urllib.request.urlretrieve(url, dst)
        print("ok  ", cid)
    except Exception as e:
        print("FAIL", cid, e)
PY
echo "done -> $OUT/  (videos + manifest.json)"
