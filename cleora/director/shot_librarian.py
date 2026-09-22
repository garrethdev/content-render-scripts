#!/usr/bin/env python3
"""Shot Librarian — generate-gap side of the self-extending Cleora Director.

When the Director cannot find a library clip that genuinely depicts a beat, it emits a `generate`
request. This module is the deterministic half of filling that gap: it builds a house-style prompt,
and (after the agent generates the clip through Higgsfield) uploads the clip + still to Supabase
storage and inserts a fully tagged `cleora_clips` row so the shot becomes reusable inventory.

Style anchor distilled from _docs/method__VISUAL_CONSISTENCY_SPEC.md (+ the locked golden-hour palette)
and the cadence tail from _docs/GENERIC_CLEORA_BROLL_PACK.md.

CLI:
  python shot_librarian.py prompt   --json '<req>'                 # print the generation prompt
  python shot_librarian.py dedup    --action '<what it shows>'     # print an existing shot_key or ""
  python shot_librarian.py add      --json '<req>' --mp4 f.mp4 [--still s.png] --source CLE-B6-0004:2
"""
import argparse, json, os, re, subprocess, sys, urllib.request, urllib.error

KEY = os.environ.get('SUPABASE_KEY','')
REST = 'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1'
STOR = 'https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object'
PUB  = 'https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/public'
BUCKET = 'cleora-clips'

STYLE_ANCHOR = (
    "Handmade stop-motion claymation inside Madame Cleora's miniature parlour. Modeling clay with "
    "visible tool marks, fingerprints and faint painted brush strokes, slightly asymmetrical, strictly "
    "matte to low-satin finish. Lighting: a hard low warm key about 2800K like candle or lantern light, "
    "plus a soft high cool violet fill about 5000K; high contrast, shadows tinted deep blue-purple, "
    "never pure black. Palette: deep royal purple, rich teal, warm dark wood-brown, aged antique gold, "
    "and a magical magenta glow; golden-hour-midpoint grade, colours held rich not washed out. "
    "Medium-telephoto 50-85mm look, very shallow depth of field with soft bokeh, eye-level, 9:16 "
    "vertical. Fine organic film grain and gentle cinematic softness, lifted charcoal blacks."
)
CADENCE_TAIL = (
    "Animated on twos, stepped 12fps stop-motion cadence, poses held then snapped to the next, no "
    "motion blur, tiny frame-to-frame jitter and boil in the clay and fabric, camera locked off on a "
    "tripod, subtle motion only, silent."
)
BAN = (
    "Avoid: smooth symmetrical polished clay, CGI, 3D render, Pixar style, photorealistic skin, wet "
    "eyes, flat or even or studio lighting, bright high-key, deep focus, background sharpness, digital "
    "sharpness, wide-angle or fisheye distortion, neon or primary colours."
)

STOP = set("a an the of to in on at for and or with it its is are was were be been that this into "
           "as by from up out over under then them they their your you her his".split())


def slug(action):
    words = [w for w in re.findall(r"[a-z0-9]+", (action or '').lower()) if w not in STOP]
    return ("gen_" + "_".join(words[:4]))[:48] or "gen_shot"


def build_prompt(req):
    return f"{req.get('action','').strip().rstrip('.')}. {STYLE_ANCHOR} {CADENCE_TAIL} {BAN}"


def _get(path):
    r = urllib.request.Request(f"{REST}/{path}", headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'})
    with urllib.request.urlopen(r, timeout=30) as f:
        return json.load(f)


def dedup(action):
    """Return an existing active shot_key whose action strongly overlaps, else ''."""
    want = {w for w in re.findall(r"[a-z0-9]+", (action or '').lower()) if w not in STOP and len(w) > 2}
    if not want:
        return ''
    rows = _get("cleora_clips?status=eq.active&select=shot_key,action")
    best, best_score = '', 0.0
    for row in rows:
        have = {w for w in re.findall(r"[a-z0-9]+", (row.get('action') or '').lower())
                if w not in STOP and len(w) > 2}
        if not have:
            continue
        score = len(want & have) / len(want)
        if score > best_score:
            best, best_score = row['shot_key'], score
    return best if best_score >= 0.6 else ''


def _probe(path):
    def q(entries, stream=None):
        cmd = ['ffprobe', '-v', 'error', '-show_entries', entries, '-of', 'csv=p=0', path]
        if stream:
            cmd[4:4] = ['-select_streams', stream]
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
    dur = float((q('format=duration') or ['5'])[0] or 5)
    wh = (q('stream=width,height', 'v:0') or ['1080', '1920'])
    w = int(wh[0]); h = int(wh[1]) if len(wh) > 1 else 1920
    return round(dur, 3), w, h


def _upload(local, dest, ctype):
    data = open(local, 'rb').read()
    req = urllib.request.Request(f"{STOR}/{BUCKET}/{dest}", data=data, method='POST',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': ctype,
                 'x-upsert': 'true'})
    try:
        with urllib.request.urlopen(req, timeout=180) as f:
            f.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        if 'exist' not in body.lower():
            raise RuntimeError(f"upload {dest} failed: {e.code} {body}")
    return f"{PUB}/{BUCKET}/{dest}"


def add_clip(req, mp4, still, source):
    shot_key = req.get('shot_key') or slug(req.get('action', ''))
    dur, w, h = _probe(mp4)
    vpath = f"_generated/{shot_key}.mp4"
    vurl = _upload(mp4, vpath, 'video/mp4')
    surl = None
    if still and os.path.exists(still):
        surl = _upload(still, f"_generated/{shot_key}.png", 'image/png')
    row = {
        'shot_key': shot_key, 'action': req.get('action', ''), 'beat_role': req.get('beat_role', ''),
        'mood': req.get('mood', ''), 'framing': req.get('framing', ''),
        'subject_gender': req.get('subject_gender', 'neutral'),
        'vo_safe': True, 'talk_capable': False, 'can_open': False, 'silent_broll': True,
        'duration_seconds': dur, 'width': w, 'height': h,
        'video_storage_path': vpath, 'video_public_url': vurl, 'still_frame': surl,
        'status': 'active', 'tags': ['auto', 'generated', 'cleora'], 'usage_count': 0,
        'notes': f"auto-gen for {source}",
    }
    body = json.dumps(row).encode()
    r = urllib.request.Request(f"{REST}/cleora_clips", data=body, method='POST',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json',
                 'Prefer': 'return=minimal'})
    try:
        with urllib.request.urlopen(r, timeout=30) as f:
            f.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"insert {shot_key} failed: {e.code} {e.read().decode()[:200]}")
    return {'shot_key': shot_key, 'video_public_url': vurl, 'duration_seconds': dur}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prompt', 'dedup', 'add'])
    ap.add_argument('--json', help='generate-request JSON (action, beat_role, subject_gender, mood, framing, [shot_key])')
    ap.add_argument('--action')
    ap.add_argument('--mp4'); ap.add_argument('--still'); ap.add_argument('--source', default='manual')
    o = ap.parse_args()
    if o.cmd == 'prompt':
        print(build_prompt(json.loads(o.json)))
    elif o.cmd == 'dedup':
        print(dedup(o.action or (json.loads(o.json).get('action') if o.json else '')))
    elif o.cmd == 'add':
        print(json.dumps(add_clip(json.loads(o.json), o.mp4, o.still, o.source)))


if __name__ == '__main__':
    main()
