"""Captions via the Universal Caption Maker (table-driven n8n job).

It reads rows from a Supabase table, generates a spec-compliant caption per row (lifestyle voice, GLP-1/
peptide/drug bans + ampersand/dash rules already built in), and PATCHes them back into target_column.
We point it at pod_content and let it fill `caption`.
"""
import os, json, urllib.request
from . import config

WEBHOOK = os.environ.get("CAPTION_WEBHOOK", "https://czed.app.n8n.cloud/webhook/caption-maker")

# health/wellness hashtag pool (the default pool is generic lifestyle; give it ours)
HASHTAG_POOL = ["#wellness", "#healthylifestyle", "#weightlosstips", "#cravings", "#foodfreedom",
                "#healthjourney", "#metabolichealth", "#guthealth", "#hormonebalance", "#healthyhabits",
                "#nutritiontips", "#bloating", "#energy", "#healthtok", "#wellnesstok"]

def run_caption_maker(batch, only_missing=True):
    """Fire the caption maker over one batch of pod_content. Returns the run summary dict."""
    flt = f"batch=eq.{batch}"
    if only_missing:
        flt += "&caption=is.null"
    payload = {
        "source": {
            "table": "pod_content",
            "supabase_url": config.SUPABASE_URL,
            "filter": flt,
            "id_column": "id",
            "context_columns": ["hook", "title", "show", "host"],
            "limit": 500,
        },
        "output": {"target_column": "caption", "timestamp_column": "captioned_at"},
        "format": {"hashtag_pool": HASHTAG_POOL, "hashtag_count": 3},
        "concurrency": 5,
    }
    r = urllib.request.Request(WEBHOOK, data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read())
