"""Central config: env loading, paths, keys, constants. Import this everywhere else."""
import os

# podcast_lane/ lives inside the viral-filler-mover repo; ROOT is that repo dir.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV  = os.path.join(ROOT, "..", "viral-content-filler-creator", ".env")

def _load_env(path):
    """Populate os.environ from a KEY=VALUE .env (does not overwrite existing vars)."""
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env(ENV)

# --- credentials / endpoints ---
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]
OPENROUTER_KEY = os.environ["OPENROUTER_KEY"]
BUCKET = os.environ.get("VIRAL_FILLER_BUCKET", "viral-filler")

# --- models ---
# cheaper/faster defaults (override via env if quality needs it)
HOOK_MODEL   = os.environ.get("HOOK_MODEL",   "anthropic/claude-haiku-4.5")
VISION_MODEL = os.environ.get("VISION_MODEL", "google/gemini-2.5-flash")
TOPIC_MODEL  = os.environ.get("TOPIC_MODEL",  "anthropic/claude-haiku-4.5")
CAPTION_MODEL = os.environ.get("CAPTION_MODEL", "anthropic/claude-haiku-4.5")

# --- render ---
CHARS = ["char2", "char3", "char4"]   # PiP cutouts, rotated by clip index
CUT_H_FRAC = 0.192                     # PiP height as fraction of frame
FFMPEG  = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

# --- external scripts (siblings in ROOT) ---
FILLER_MOVER = os.path.join(ROOT, "filler_mover.py")
PROBE_BASE   = os.path.join(ROOT, "probe_base.py")

# --- work dirs ---
WORK = os.path.join(ROOT, "work", "podcast_worker")
BASE = os.path.join(WORK, "base")
OUT  = os.path.join(WORK, "out")
for _d in (BASE, OUT):
    os.makedirs(_d, exist_ok=True)
