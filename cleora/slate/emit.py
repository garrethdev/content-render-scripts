import json,sys
B='/home/user/calesthio/openmontage/projects/cleora-batch'
j=json.load(open(f'{B}/slate/tts_jobs.json'))
V='f090ee08-4376-414b-9260-d6af0cbd85c8'
pend=[i for i,x in enumerate(j) if not x.get('url') and not x.get('job_id')]
n=int(sys.argv[1]) if len(sys.argv)>1 else 24
req=[{'index':i,'params':{'model':'seed_audio','prompt':j[i]['text'],'voice_type':'element','voice_id':V}} for i in pend[:n]]
sys.stderr.write(f"pending {len(pend)}, emitting {len(req)}\n")
print(json.dumps(req,ensure_ascii=False))
