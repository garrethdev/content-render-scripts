"""Emit the next N seed_audio requests for the unvoiced slate episodes only.

emit.py takes whatever is pending across the whole job file, which now includes leftover redo rows for
episodes that are already voiced. This restricts the batch to episodes with no cached wavs, so a submit
wave cannot spend credit re-reading an episode that is already done.
"""
import json, os, sys
B = '/home/user/calesthio/openmontage/projects/cleora-batch'
V = 'f090ee08-4376-414b-9260-d6af0cbd85c8'
KEYS = ('hook', 'story', 'turn', 'closer')
j = json.load(open(f'{B}/slate/tts_jobs.json'))
m = json.load(open(f'{B}/slate/epmap.json'))
unvoiced = {ep for ep in m.values()
            if not all(os.path.exists(f'{B}/audio/{ep}_{k}.wav') for k in KEYS)}
pend = [i for i, x in enumerate(j)
        if x['ep'] in unvoiced and not x.get('url') and not x.get('job_id')]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
req = [{'index': i, 'params': {'model': 'seed_audio', 'prompt': j[i]['text'],
                               'voice_type': 'element', 'voice_id': V}} for i in pend[:n]]
sys.stderr.write(f'unvoiced {len(unvoiced)} eps, pending {len(pend)} reads, emitting {len(req)}\n')
print(json.dumps(req, ensure_ascii=False))
