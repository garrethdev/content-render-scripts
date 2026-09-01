"""Hook vs caption detection = VISION-OCR + SPEECH-MATCH (deterministic decision).

The reliable idea: a CAPTION is the speaker's own words (matches the audio); a HOOK is editorial text the
creator added that the speaker is NOT saying. We split the job into each tool's strength:
  1. A vision model READS the burned-in overlay text verbatim (accurate on stylized text; no OCR garble).
  2. Whisper transcribes the opening audio -> the words actually spoken.
  3. Deterministic compare: overlay words that are NOT spoken = editorial = hook -> hide ours.
     Overlay words that ARE spoken = captions -> add ours.
No flaky "is this a hook?" judgment — the model only reads; the decision is rule-based.
"""
import os, subprocess, json, re, base64
from . import config, openrouter

_AUDIO_PY   = os.path.expanduser("~/Claude/.audio-venv/bin/python")
_TRANSCRIBE = os.path.join(config.ROOT, "transcribe_open.py")

_MIN_LEN   = 4
_NONSPOKEN = 2      # this many substantial overlay words NOT spoken => hook

_READ_PROMPT = (
    "These frames are from the opening of a vertical short video. Read ALL prominent burned-in TEXT OVERLAYS "
    "you can see across these frames, verbatim (big headlines, hooks, titles, and caption words). "
    "IGNORE tiny logos, channel handles, @usernames, and watermarks. "
    "Return ONLY a JSON array of the distinct text lines, e.g. [\"WE CAN REVERSE GREY HAIR\", \"had stage four\"]. "
    "If there is no overlay text, return []."
)

# ---- 1. vision reads the overlay text ----
def _frames(base, duration):
    # only the OPENING matters: our hook shows at the start, so a late caption/hook can't collide with it
    imgs = []
    for i, t in enumerate([t for t in (0.5, 1.5, 2.5, 3.5, 5.0) if t < duration]):
        p = os.path.join(config.WORK, f"hr_{i}.jpg")
        subprocess.run([config.FFMPEG, "-y", "-ss", str(t), "-i", base, "-frames:v", "1",
                        "-vf", "scale=480:-1", p], capture_output=True, timeout=60)
        if os.path.exists(p):
            imgs.append(p)
    return imgs

def _read_overlays(base, duration):
    """Return list[str] of overlay lines, or None if the read failed."""
    imgs = _frames(base, duration)
    if not imgs:
        return []
    content = [{"type": "text", "text": _READ_PROMPT}]
    for p in imgs:
        b = base64.b64encode(open(p, "rb").read()).decode()
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}})
    for attempt in range(2):   # retry once — the reasoning model occasionally returns an empty body
        try:
            reply = openrouter.chat(config.VISION_MODEL, [{"role": "user", "content": content}], max_tokens=1500)
            arr = openrouter.extract_json(reply)
            return [str(x) for x in arr] if isinstance(arr, list) else []
        except Exception as e:
            print(f"   overlay read attempt {attempt+1} failed:", e)
    return None

# ---- 2. whisper transcribes the opening ----
def _spoken(base):
    # transcribe the opening (a little past 6s so captions near the edge still match)
    wav = os.path.join(config.WORK, "hs_open.wav")
    subprocess.run([config.FFMPEG, "-y", "-t", "8", "-i", base,
                    "-ar", "16000", "-ac", "1", wav], capture_output=True, timeout=90)
    if not os.path.exists(wav):
        return set()
    r = subprocess.run([_AUDIO_PY, _TRANSCRIBE, wav], capture_output=True, text=True, timeout=180)
    try:
        return set(json.loads(r.stdout))
    except Exception:
        return set()

def _is_spoken(word, spoken):
    if word in spoken:
        return True
    stem = word[:5]
    return any(s.startswith(stem) or word.startswith(s[:5]) for s in spoken)

# ---- 3. deterministic decision ----
def _words(lines):
    out = set()
    for line in lines:
        for w in re.split(r"\s+", line.lower()):
            tok = re.sub(r"[^a-z]", "", w)
            if len(tok) >= _MIN_LEN and any(v in tok for v in "aeiou"):
                out.add(tok)
    return out

def detect(base, duration):
    """Return (hook: bool, reason). hook=True => clip already has its own editorial hook; hide ours."""
    lines = _read_overlays(base, duration)
    if lines is None:
        return True, "overlay read failed; assume hook (avoid double)"
    onscreen = _words(lines)
    if not onscreen:
        return False, "no overlay text -> clean"
    spoken = _spoken(base)
    if not spoken:
        return True, "no transcript; overlay present, assume hook"
    editorial = sorted(w for w in onscreen if not _is_spoken(w, spoken))
    if len(editorial) >= _NONSPOKEN:
        return True, f"editorial overlay not spoken: {editorial[:5]}"
    return False, f"overlay matches speech (captions); editorial={editorial}"
