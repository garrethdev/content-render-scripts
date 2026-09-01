"""Media I/O: download shorts, probe duration, sample frames, build the placement manifest, render."""
import os, base64, subprocess
from . import config

def download(video_id, url):
    """yt-dlp the short to work/base/<id>.mp4 (cached). Returns path or None."""
    dst = os.path.join(config.BASE, f"{video_id}.mp4")
    if os.path.exists(dst):
        return dst
    subprocess.run(["yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", dst, url],
                   capture_output=True, text=True, timeout=240)
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
        subprocess.run(["python3", config.PROBE_BASE, base, man, str(config.CUT_H_FRAC)],
                       capture_output=True, text=True, timeout=420)
    except Exception as e:
        print("   manifest analysis failed/slow, using fallback placement:", type(e).__name__)
        return None
    return man if os.path.exists(man) else None

def render(base, character, seed, caption, out, manifest=None):
    """Invoke filler_mover to composite base + drifting PiP + (optional) hook. Returns success bool."""
    cmd = ["python3", config.FILLER_MOVER, "--base", base, "--character", character,
           "--seed", str(seed), "--caption", caption, "--cut-h-frac", str(config.CUT_H_FRAC),
           "--out", out]
    if manifest:
        cmd += ["--manifest", manifest]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return os.path.exists(out)
