"""Write the per-episode tts.json the render wrapper takes. Reads are already cached in audio/, so the
urls are only a fallback; turn_at must match the split the reads were generated from."""
import json,os
B='/home/user/calesthio/openmontage/projects/cleora-batch'
j=json.load(open(f'{B}/slate/tts_jobs.json')); m=json.load(open(f'{B}/slate/epmap.json'))
rev={v:k for k,v in m.items()}; os.makedirs(f'{B}/slate/tts',exist_ok=True)
by={}
for x in j: by.setdefault(x['ep'],{})[x['key']]=x
ready=[]
for ep,d in by.items():
    if len(d)<4 or not all(v.get('url') for v in d.values()): continue
    cid=rev[ep]; r=json.load(open(f'{B}/slate/reads/{cid}.reads.json'))
    o={k:d[k]['url'] for k in ('hook','story','turn','closer')}; o['turn_at']=r['turn_at']
    json.dump(o,open(f'{B}/slate/tts/{ep}.json','w'),indent=1); ready.append(ep)
print('episodes with all 4 reads:',len(ready)); print(' '.join(sorted(ready)))
