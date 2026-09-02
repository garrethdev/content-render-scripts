"""Media I/O: download shorts, probe duration, sample frames, build the placement manifest, render."""
import os, sys, base64, subprocess
from . import config

# Run child scripts with the SAME interpreter as the worker (the venv that has
# Pillow/opencv), not a bare "python3" that resolves to whatever is on PATH.
PYTHON = os.environ.get("POD_PYTHON", sys.executable)

def download(video_id, url):
    """yt-dlp the short to work/base/<id>.mp4 (cached). Returns path or None.
    YouTube 403s unauthenticated datacenter-style requests; set YTDLP_COOKIES_BROWSER
    (e.g. chrome|firefox|safari|edge) to pull a logged-in session's cookies."""
    dst = os.path.join(config.BASE, f"{video_id}.mp4")
    if os.path.exists(dst):
        return dst
    cmd = ["yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4"]
    cookies_browser = os.environ.get("YTDLP_COOKIES_BROWSER")
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd += ["-o", dst, url]
    subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    return dst if os.path.exists(dst) else None

def probe_duration(base):
    r = subprocess.run([config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", base], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 60.0

def frame_b64(base, t, tmp=None):
    """Extract a single downscaled JPEG frame at time t, return base64 (or None)."""
    tmp = tmp or os.path.join(config.WORK, "f.jpg")
    subprocess.run([config.FFMPEG, "-y", "-ss", str(t), "-i", base, "-frames:v", "1",
                    "-vf", "scale=360:-1", tmp], capture_output=True, text=True, timeout=60)
    if not os.path.exists(tmp):
        return None
    return base64.b64encode(open(tmp, "rb").read()).decode()

def make_manifest(base):
    """Run probe_base.py (face + burned-text analysis) -> manifest path for face-aware placement.

    Best-effort: on timeout/failure return None so the render still runs (static-corner fallback)
    instead of crashing the whole batch.
    """
    man = base + ".manifest.json"
    if os.path.exists(man):
        return man
    try:
        subprocess.run([PYTHON, config.PROBE_BASE, base, man, str(config.CUT_H_FRAC)],
                       capture_output=True, text=True, timeout=420)
    except Exception as e:
        print("   manifest analysis failed/slow, using fallback placement:", type(e).__name__)
        return None
    return man if os.path.exists(man) else None

def render(base, character, seed, caption, out, manifest=None):
    """Invoke filler_mover to composite base + drifting PiP + (optional) hook. Returns success bool."""
    cmd = [PYTHON, config.FILLER_MOVER, "--base", base, "--character", character,
           "--seed", str(seed), "--caption", caption, "--cut-h-frac", str(config.CUT_H_FRAC),
           "--out", out]
    if manifest:
        cmd += ["--manifest", manifest]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return os.path.exists(out)
