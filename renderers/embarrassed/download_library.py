#!/usr/bin/env python3
"""
Bulk-download all approved embarrassed_angle_sources videos to local cache.
Resolves TikTok + Instagram via ScrapeCreators.
YouTube Shorts via yt-dlp (must be installed: brew install yt-dlp).
Twitter/X via yt-dlp as well.

Updates video_public_url + video_storage_path on each row once downloaded.

Usage:
  python download_library.py              # download all pending
  python download_library.py --id 6      # single row
  python download_library.py --dry-run   # show what would be downloaded
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# ── env ───────────────────────────────────────────────────────────────────────
for line in open(os.path.expanduser("~/.config/peptide-secrets/.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

SB_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"
SB_KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY") or os.environ.get("CAROUSEL_SUPABASE_PUBLISHABLE_KEY")
SCK    = os.environ.get("SCRAPECREATORS_API_KEY", "")

if not SB_KEY:
    sys.exit("ERROR: CAROUSEL_SUPABASE_SECRET_KEY not found in env")

_HERE    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.environ.get("EMBARRASSED_CACHE_DIR", os.path.join(_HERE, "cache"))
os.makedirs(CACHE_DIR, exist_ok=True)

TABLE = "embarrassed_angle_sources"

_TT_UA = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://www.tiktok.com/",
}

# ── Supabase ──────────────────────────────────────────────────────────────────
def _sb_headers():
    return {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}",
            "Content-Type": "application/json"}

def sb_get(qs):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{TABLE}?{qs}", headers=_sb_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def sb_patch(row_id, body):
    url = f"{SB_URL}/rest/v1/{TABLE}?id=eq.{row_id}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH",
          headers={**_sb_headers(), "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# ── ScrapeCreators ────────────────────────────────────────────────────────────
def _sc(url):
    req = urllib.request.Request(url, headers={"x-api-key": SCK})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def resolve_tiktok(page_url):
    v = _sc("https://api.scrapecreators.com/v2/tiktok/video?" +
            urllib.parse.urlencode({"url": page_url}))["aweme_detail"]["video"]
    for k in ("play_addr_h264", "download_no_watermark_addr", "play_addr"):
        try:
            return v[k]["url_list"][0]
        except Exception:
            pass
    raise RuntimeError("no TikTok play URL from ScrapeCreators")

def resolve_instagram(page_url):
    d = _sc("https://api.scrapecreators.com/v2/instagram/post?" +
            urllib.parse.urlencode({"url": page_url}))
    vurl = d.get("video_url")
    if not vurl:
        acc = []
        def fv(o):
            if isinstance(o, dict):
                for k2, v2 in o.items():
                    if isinstance(v2, str) and v2.startswith("http") and (".mp4" in v2 or k2.lower() == "video_url"):
                        acc.append(v2)
                    fv(v2)
            elif isinstance(o, list):
                for v2 in o: fv(v2)
        fv(d); vurl = acc[0] if acc else None
    if not vurl:
        raise RuntimeError("no Instagram video URL")
    return vurl

# ── yt-dlp (YouTube Shorts, Twitter/X) ───────────────────────────────────────
def download_ytdlp(page_url, out_path):
    """Download via yt-dlp — works for YouTube Shorts and Twitter/X."""
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_path,
        page_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")
    return out_path

# ── download helpers ──────────────────────────────────────────────────────────
def download_direct(url, out, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=300) as resp, open(out, "wb") as f:
        f.write(resp.read())
    return out

def cache_path(row):
    return os.path.join(CACHE_DIR, f"clip_a_{row['aweme_id']}.mp4")

def is_cached(row):
    p = cache_path(row)
    return os.path.exists(p) and os.path.getsize(p) > 0

# ── per-row download ──────────────────────────────────────────────────────────
def download_row(row, dry_run=False):
    rid      = row["id"]
    platform = row.get("platform", "tiktok")
    url      = row["url"]
    out      = cache_path(row)

    if is_cached(row):
        print(f"  [{rid}] already cached — skipping")
        # still write path to Supabase if missing
        if not row.get("video_public_url"):
            if not dry_run:
                sb_patch(rid, {"video_public_url": out, "video_storage_path": out})
            print(f"  [{rid}] updated Supabase path")
        return True

    print(f"  [{rid}] {platform} {url}")
    if dry_run:
        print(f"         → would download to {out}")
        return True

    try:
        if platform == "instagram":
            play_url = resolve_instagram(url)
            download_direct(play_url, out)
        else:
            # TikTok, YouTube, Twitter/X — yt-dlp, no ScrapeCreators credits
            download_ytdlp(url, out)

        size_mb = os.path.getsize(out) / 1_000_000
        print(f"  [{rid}] downloaded {size_mb:.1f} MB → {os.path.basename(out)}")
        sb_patch(rid, {"video_public_url": out, "video_storage_path": out})
        print(f"  [{rid}] Supabase updated")
        return True

    except Exception as e:
        print(f"  [{rid}] FAILED: {e}")
        if os.path.exists(out) and os.path.getsize(out) == 0:
            os.unlink(out)
        return False

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=None, help="Download single row by ID")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="Seconds between ScrapeCreators calls (default 1.5)")
    args = ap.parse_args()

    if args.id:
        rows = sb_get(f"id=eq.{args.id}&select=*")
    else:
        rows = sb_get("status=eq.approved&select=*&order=id.asc")

    print(f"{'DRY RUN — ' if args.dry_run else ''}processing {len(rows)} rows")

    ok = fail = skip = 0
    for i, row in enumerate(rows):
        already = is_cached(row) and bool(row.get("video_public_url"))
        if already:
            skip += 1
            print(f"  [{row['id']}] cached+Supabase OK — skip")
            continue

        success = download_row(row, dry_run=args.dry_run)
        if success:
            ok += 1
        else:
            fail += 1

        # throttle between API calls to avoid rate-limiting
        if not args.dry_run and i < len(rows) - 1:
            time.sleep(args.delay)

    print(f"\ndone: {ok} downloaded, {skip} already cached, {fail} failed")

if __name__ == "__main__":
    main()
