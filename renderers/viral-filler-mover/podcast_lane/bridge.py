"""Bridge: finished podcast_renders -> pod_content (the Smart Scheduler's POD table).

Writes scheduler-ready-shaped rows: video_url, hook, caption(filled later), character(+variation), show/host/
title, gatekeep_status='approved' (auto-pass on successful render + hook detection), batch. Leaves every
scheduler-owned column NULL and scheduler_ready=false. content_id auto-generates (POD-NNN). Idempotent on
source_video_id.
"""
import json
from . import supa, config

def _char_variation(character):
    # 'char2' -> 2
    return int("".join(c for c in (character or "") if c.isdigit()) or 0) or None

def _titles_for(video_ids):
    if not video_ids:
        return {}
    ids = ",".join(f'"{v}"' for v in video_ids)
    q = f"{config.SUPABASE_URL}/rest/v1/podcast_clips?video_id=in.({ids})&select=video_id,title"
    rows = json.loads(supa._req("GET", q, supa._headers())[1])
    return {r["video_id"]: r.get("title") for r in rows}

def build_pod(batch, limit=None):
    """Insert/upsert pod_content rows for all finished renders. Returns count staged."""
    q = (f"{config.SUPABASE_URL}/rest/v1/podcast_renders?status=eq.done&render_url=not.is.null"
         f"&select=clip_video_id,show,host,hook,character,render_url")
    if limit:
        q += f"&limit={limit}"
    renders = json.loads(supa._req("GET", q, supa._headers())[1])
    # only bridge renders not already in pod_content (don't re-stamp/re-caption prior batches)
    existing = json.loads(supa._req(
        "GET", f"{config.SUPABASE_URL}/rest/v1/pod_content?select=source_video_id", supa._headers())[1])
    seen = {e["source_video_id"] for e in existing}
    renders = [r for r in renders if r["clip_video_id"] not in seen]
    titles = _titles_for([r["clip_video_id"] for r in renders])
    rows = [{
        "source_video_id": r["clip_video_id"],
        "show": r.get("show"), "host": r.get("host"),
        "title": titles.get(r["clip_video_id"]),
        "video_url": r["render_url"], "hook": r.get("hook"),
        "character": r.get("character"), "character_variation": _char_variation(r.get("character")),
        "gatekeep_status": "approved",          # auto-pass: render + hook-detection already succeeded
        "batch": batch, "scheduler_ready": False,
    } for r in renders]
    if not rows:
        return 0
    supa._req("POST",
              f"{config.SUPABASE_URL}/rest/v1/pod_content?on_conflict=source_video_id",
              supa._headers({"Content-Type": "application/json",
                             "Prefer": "resolution=merge-duplicates,return=minimal"}),
              json.dumps(rows).encode())
    return len(rows)

def release(batch):
    """Flip scheduler_ready=true for a finished, approved, caption-filled batch."""
    q = (f"{config.SUPABASE_URL}/rest/v1/pod_content?batch=eq.{batch}"
         f"&gatekeep_status=eq.approved&caption=not.is.null&posting_status=is.null")
    supa._req("PATCH", q, supa._headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
              json.dumps({"scheduler_ready": True}).encode())
