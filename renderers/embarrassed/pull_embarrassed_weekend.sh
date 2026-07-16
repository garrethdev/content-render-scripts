#!/usr/bin/env bash
# Pull ONLY the Embarrassed videos produced this weekend (created after 2026-07-04 15:45 UTC):
# 51 pieces = 23 laugh-track + 28 voiceover. Public bucket, no auth needed to download.
# Usage: bash pull_embarrassed_weekend.sh [outdir]
set -euo pipefail

# load secrets from the machine-local env (never hardcode the key)
[ -f "$HOME/.config/peptide-secrets/.env" ] && set -a && . "$HOME/.config/peptide-secrets/.env" && set +a
SB="${SUPABASE_URL:-https://qlcmgxgwpzmiebzxflai.supabase.co}"
ANON="${SUPABASE_ANON_KEY:?set SUPABASE_ANON_KEY in ~/.config/peptide-secrets/.env or the environment}"
CUTOFF="2026-07-04T15:45:00Z"           # start of Friday's batch = the 72-hour window
OUT="${1:-embarrassed_weekend}"
mkdir -p "$OUT"

# manifest: only rows rendered AFTER the cutoff (this weekend's batch)
curl -s "$SB/rest/v1/embarrassed_angle_content?stitch_status=eq.rendered&created_at=gt.$CUTOFF&select=content_id,text_hook,caption,video_public_url,created_at&order=content_id" \
  -H "apikey: $ANON" -H "Authorization: Bearer $ANON" > "$OUT/manifest.json"

python3 - "$OUT" <<'PY'
import json, os, sys, urllib.request
out = sys.argv[1]
# the 23 laugh-track content_ids (the rest of the batch is voiceover)
LAUGH = {"EA-001-V4","EA-001-V6","EA-021-V5","EA-022-V4","EA-022-V6","EA-026-V5",
         "EA-028-V4","EA-028-V6","EA-030-V5","EA-031-V4","EA-031-V6","EA-041-V2",
         "EA-045-V1","EA-045-V3","EA-046-V2","EA-048-V1","EA-048-V3","EA-049-V2",
         "EA-053-V2","EA-055-V1","EA-055-V3","EA-067-V2","EA-068-V1"}
rows = json.load(open(f"{out}/manifest.json"))
laugh = sum(1 for r in rows if r["content_id"] in LAUGH)
print(f"{len(rows)} weekend videos  ({laugh} laugh, {len(rows)-laugh} voiceover)")
# tag each row + download into laugh/ or voiceover/ subfolders
for sub in ("laugh","voiceover"): os.makedirs(os.path.join(out, sub), exist_ok=True)
for r in rows:
    cid = r["content_id"]
    r["audio"] = "laugh" if cid in LAUGH else "voiceover"
    dst = os.path.join(out, r["audio"], f"{cid}.mp4")
    if os.path.exists(dst): continue
    try:
        urllib.request.urlretrieve(r["video_public_url"], dst); print("ok  ", r["audio"], cid)
    except Exception as e:
        print("FAIL", cid, e)
json.dump(rows, open(f"{out}/manifest.json","w"), indent=1)  # manifest now carries the audio tag
PY
echo "done -> $OUT/  (laugh/ + voiceover/ subfolders, manifest.json with audio tags)"
