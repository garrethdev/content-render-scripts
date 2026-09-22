"""Upload finished episode SFX renders to Supabase storage and record the public URL.

Uploads to:  cleora-clips/episodes/<ep>/<filename>.mp4
Updates:     cleora_content.video_storage_path, .video_public_url, .render_status, .rendered_at

Usage:
  python3 slate/upload_episodes.py           # dry run (shows what would upload)
  python3 slate/upload_episodes.py --apply   # upload + patch DB
"""
import glob, json, os, subprocess, sys
from datetime import datetime, timezone

KEY = os.environ.get('SUPABASE_KEY','')
CA  = '/root/.ccr/ca-bundle.crt'
REST = 'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'
STOR = 'https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object'
PUB  = 'https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/public'
BUCKET = 'cleora-clips'
PROJ = '/home/user/calesthio/openmontage/projects'
H = ['-H', f'apikey: {KEY}', '-H', f'Authorization: Bearer {KEY}']
APPLY = '--apply' in sys.argv

def curl(*args):
    return subprocess.run(['curl', '-s', '--cacert', CA] + list(args), capture_output=True, text=True)

# Load epmap: content_id -> ep_name
epmap = json.load(open(os.path.join(os.path.dirname(__file__), 'epmap.json')))
ep2cid = {v: k for k, v in epmap.items()}  # ep_name -> content_id

def best_render(ep):
    """Prefer the SFX render; fall back to base render."""
    sfx = sorted(glob.glob(f'{PROJ}/cleora-{ep}-*/renders/{ep}_*sfx*.mp4'))
    if sfx:
        return sfx[-1]
    base = sorted(glob.glob(f'{PROJ}/cleora-{ep}-*/renders/{ep}_*.mp4'))
    return base[-1] if base else None

# Batch fetch all upload statuses in one query
all_cids = ','.join(f'"{c}"' for c in ep2cid.values())
r = curl(f'{REST}?content_id=in.({all_cids})&select=content_id,video_public_url', *H)
uploaded_cids = {row['content_id'] for row in json.loads(r.stdout) if row.get('video_public_url')}

todo = []
for ep in sorted(ep2cid):
    cid = ep2cid[ep]
    path = best_render(ep)
    if not path:
        print(f'  SKIP {ep}: no render found')
        continue
    uploaded = cid in uploaded_cids
    sfx_tag = '(sfx)' if 'sfx' in os.path.basename(path) else '(base)'
    status = 'ALREADY UP' if uploaded else 'NEED UPLOAD'
    print(f'  {ep} {status} {sfx_tag}: {os.path.basename(path)}')
    if not uploaded:
        todo.append((ep, cid, path))

print(f'\n{len(todo)} episodes to upload')
if not APPLY:
    print('Re-run with --apply to upload.')
    sys.exit(0)

for i, (ep, cid, path) in enumerate(todo, 1):
    fname = os.path.basename(path)
    storage_path = f'episodes/{ep}/{fname}'
    upload_url = f'{STOR}/{BUCKET}/{storage_path}'
    public_url = f'{PUB}/{BUCKET}/{storage_path}'

    print(f'[{i}/{len(todo)}] {ep}: uploading {fname} ({os.path.getsize(path)//1024//1024}MB)...', end=' ', flush=True)
    r = curl('-X', 'POST', upload_url,
             '-H', 'Content-Type: video/mp4',
             '-H', f'apikey: {KEY}', '-H', f'Authorization: Bearer {KEY}',
             '--data-binary', f'@{path}')
    if r.returncode != 0 or (r.stdout and 'error' in r.stdout.lower() and 'already' not in r.stdout.lower()):
        print(f'UPLOAD ERR: {r.stdout[:200]}')
        continue

    # Patch DB
    now = datetime.now(timezone.utc).isoformat()
    body = json.dumps({
        'video_storage_path': storage_path,
        'video_public_url': public_url,
        'render_status': 'rendered',
        'rendered_at': now,
    })
    r2 = curl('-X', 'PATCH', f'{REST}?content_id=eq.{cid}',
              *H, '-H', 'Content-Type: application/json',
              '-H', 'Prefer: return=minimal', '-d', body)
    ok = 'ok' if not r2.stdout.strip() else r2.stdout[:80]
    print(f'OK | DB: {ok}')

print('\nDone.')
