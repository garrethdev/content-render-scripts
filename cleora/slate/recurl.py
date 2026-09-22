import json,sys
B='/home/user/calesthio/openmontage/projects/cleora-batch'
P='https://d8j0ntlcm91z4.cloudfront.net/user_2ymK5JNkCPuUJQuIh0bq701c7oI/hf_'
j=json.load(open(f'{B}/slate/tts_jobs.json'))
ts=sys.argv[1]
for i in map(int,sys.argv[2:]):
    j[i]['url']=f"{P}{ts}_{j[i]['job_id']}.wav"
json.dump(j,open(f'{B}/slate/tts_jobs.json','w'),indent=1)
n=sum(1 for x in j if x.get('url')); q=sum(1 for x in j if x.get('job_id') and not x.get('url'))
print(f'urls {n}/{len(j)} | in flight {q} | not yet submitted {len(j)-n-q}')
