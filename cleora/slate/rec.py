import json,sys
B='/home/user/calesthio/openmontage/projects/cleora-batch'
j=json.load(open(f'{B}/slate/tts_jobs.json'))
for pair in sys.argv[1:]:
    i,jid=pair.split(':',1); j[int(i)]['job_id']=jid
json.dump(j,open(f'{B}/slate/tts_jobs.json','w'),indent=1)
print('with job_id:',sum(1 for x in j if x.get('job_id')),'/',len(j))
