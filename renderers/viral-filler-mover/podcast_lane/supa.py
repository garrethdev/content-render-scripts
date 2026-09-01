"""Supabase access: a tiny REST client plus the domain operations this lane needs."""
import os, json, urllib.request, urllib.error
from . import config

def _headers(extra=None):
    h = {"apikey": config.SERVICE_KEY, "Authorization": "Bearer " + config.SERVICE_KEY}
    if extra:
        h.update(extra)
    return h

def _req(method, url, headers, data=None, timeout=90):
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()

# --- podcast_clips ---
def fetch_clips(limit, on_topic=True, max_per_show=None):
    """Clean, on-topic clips, most-viewed first, capped at max_per_show each so no show dominates."""
    if max_per_show is None:
        max_per_show = int(os.environ.get("POD_MAX_PER_SHOW", "4"))
    q = (f"{config.SUPABASE_URL}/rest/v1/podcast_clips?status=eq.clean"
         f"&order=views.desc.nullslast&limit={max(limit * 8, 200)}"
         f"&select=video_id,show,host,url,title,has_onscreen_top_text,proposed_hook")
    if on_topic:
        q += "&on_topic=is.true"
    pool = json.loads(_req("GET", q, _headers())[1])
    picked, per_show = [], {}
    for c in pool:
        s = c.get("show")
        if per_show.get(s, 0) >= max_per_show:
            continue
        per_show[s] = per_show.get(s, 0) + 1
        picked.append(c)
        if len(picked) >= limit:
            break
    return picked

def patch_clip(video_id, fields):
    _req("PATCH", f"{config.SUPABASE_URL}/rest/v1/podcast_clips?video_id=eq.{video_id}",
         _headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
         json.dumps(fields).encode())

def fetch_unclassified(limit=1000):
    q = (f"{config.SUPABASE_URL}/rest/v1/podcast_clips?on_topic=is.null"
         f"&select=video_id,show,title&limit={limit}")
    _, body = _req("GET", q, _headers())
    return json.loads(body)

# --- podcast_renders ---
def insert_render(row):
    # upsert on the (clip_video_id, variant) unique key so re-renders overwrite cleanly
    _req("POST", f"{config.SUPABASE_URL}/rest/v1/podcast_renders?on_conflict=clip_video_id,variant",
         _headers({"Content-Type": "application/json",
                   "Prefer": "resolution=merge-duplicates,return=minimal"}),
         json.dumps(row).encode())

# --- storage ---
def upload_video(path, key):
    """Upload an mp4 to the bucket; return its public URL."""
    data = open(path, "rb").read()
    url = f"{config.SUPABASE_URL}/storage/v1/object/{config.BUCKET}/{key}"
    hdr = _headers({"Content-Type": "video/mp4", "x-upsert": "true"})
    try:
        _req("POST", url, hdr, data, 180)
    except urllib.error.HTTPError:
        _req("PUT", url, hdr, data, 180)
    return f"{config.SUPABASE_URL}/storage/v1/object/public/{config.BUCKET}/{key}"
