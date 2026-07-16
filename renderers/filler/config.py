"""Loads .env and exposes config. Nothing secret is hardcoded here."""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

def _load_env(path=os.path.join(_HERE, ".env")):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SERVICE_KEY     = os.environ["SUPABASE_SERVICE_KEY"]   # service_role -> can write storage + bypass RLS
PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
SCRAPECREATORS_KEY = os.environ["SCRAPECREATORS_KEY"]
OPENROUTER_KEY  = os.environ["OPENROUTER_KEY"]
N8N_BASE        = os.environ.get("N8N_BASE", "https://czed.app.n8n.cloud")

FFMPEG  = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
FONT    = os.environ.get("HOOK_FONT", os.path.join(_HERE, "assets", "hook-font.ttf"))
BUCKET  = os.environ.get("VIRAL_FILLER_BUCKET", "viral-filler")
WORKDIR = os.environ.get("WORKDIR", os.path.join(_HERE, "work"))

# queue / batching
QUEUE_STATUS = os.environ.get("QUEUE_STATUS", "queued")  # rows the worker claims
BATCH        = int(os.environ.get("BATCH", "5"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
# while idle, how often to give newly-ingested filler clips a preview thumbnail
THUMB_EVERY_SECONDS = int(os.environ.get("THUMB_EVERY_SECONDS", "300"))

os.makedirs(WORKDIR, exist_ok=True)
