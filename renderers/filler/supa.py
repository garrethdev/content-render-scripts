"""Supabase REST + Storage helpers (service-role key — full read/write)."""
import json, urllib.request, urllib.error
import config

_H = {"apikey": config.SERVICE_KEY, "Authorization": f"Bearer {config.SERVICE_KEY}"}

def rest(path, method="GET", body=None, prefer=None):
    """PostgREST call. `path` includes the table + query string, e.g. 'viral_filler_content?id=eq.5&select=*'."""
    headers = dict(_H)
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(f"{config.SUPABASE_URL}/rest/v1/{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        t = r.read().decode()
        return json.loads(t) if t else None

def upload(path_in_bucket, data_bytes, content_type):
    """Upload to the storage bucket and return the public URL."""
    req = urllib.request.Request(
        f"{config.SUPABASE_URL}/storage/v1/object/{config.BUCKET}/{path_in_bucket}",
        data=data_bytes, method="POST",
        headers={**_H, "Content-Type": content_type, "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=300)
    return f"{config.SUPABASE_URL}/storage/v1/object/public/{config.BUCKET}/{path_in_bucket}"
