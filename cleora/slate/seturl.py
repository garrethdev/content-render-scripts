"""Record a finished read's result URL against its job index.

recurl.py assumes every job in a wave shares one CloudFront timestamp; they do not - jobs finishing a
second apart get different ones. This takes the exact URL jobs_wait returned, so nothing is guessed.

  python3 seturl.py 68:https://... 70:https://...
"""
import json, sys
B = '/home/user/calesthio/openmontage/projects/cleora-batch'
j = json.load(open(f'{B}/slate/tts_jobs.json'))
for pair in sys.argv[1:]:
    i, url = pair.split(':', 1)
    j[int(i)]['url'] = url
json.dump(j, open(f'{B}/slate/tts_jobs.json', 'w'), indent=1, ensure_ascii=False)
n = sum(1 for x in j if x.get('url'))
q = sum(1 for x in j if x.get('job_id') and not x.get('url'))
print(f'urls {n}/{len(j)} | in flight {q} | not submitted {len(j) - n - q}')
