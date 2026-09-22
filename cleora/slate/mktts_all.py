"""Write a per-episode tts.json for EVERY voiced slate episode, from the cached wavs and the reads file.

mktts.py only emits a manifest when the episode's four rows in tts_jobs.json carry result URLs. Episodes
voiced in an earlier session have their wavs on disk but empty URL fields, so mktts skipped them - and any
episode re-split after its last manifest kept a stale turn_at. The renderer reuses a cached
audio/<ep>_<key>.wav and never touches the manifest URL, so the only field that must be right is turn_at:
the body-beat index where the 'turn' read begins. This regenerates all 40 from the reads file's turn_at,
pointing the (unused) URL fields at the local wavs so nothing re-downloads.
"""
import json, os
B = '/home/user/calesthio/openmontage/projects/cleora-batch'
m = json.load(open(f'{B}/slate/epmap.json')); rev = {v: k for k, v in m.items()}
os.makedirs(f'{B}/slate/tts', exist_ok=True)
K = ('hook', 'story', 'turn', 'closer')
wrote = []; missing = []
for ep in sorted(m.values()):
    wavs = {k: f'{B}/audio/{ep}_{k}.wav' for k in K}
    if not all(os.path.exists(p) and os.path.getsize(p) > 1000 for p in wavs.values()):
        missing.append(ep); continue
    rd = json.load(open(f'{B}/slate/reads/{rev[ep]}.reads.json'))
    o = {k: f'file://{wavs[k]}' for k in K}
    o['turn_at'] = rd['turn_at']
    json.dump(o, open(f'{B}/slate/tts/{ep}.json', 'w'), indent=1)
    wrote.append(ep)
print(f'wrote {len(wrote)} manifests; missing wavs for {len(missing)}: {missing}')
