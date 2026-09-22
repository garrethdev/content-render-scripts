"""Download every TTS read whose URL we have into audio/<ep>_<key>.wav (the renderer's cache slot),
normalised to 44.1k mono. Safe to re-run: an already-fetched read is skipped."""
import json,os,subprocess
B='/home/user/calesthio/openmontage/projects/cleora-batch'; CA='/root/.ccr/ca-bundle.crt'
j=json.load(open(f'{B}/slate/tts_jobs.json')); got=0; skip=0; bad=[]
for x in j:
    if not x.get('url'): continue
    out=f"{B}/audio/{x['ep']}_{x['key']}.wav"
    if os.path.exists(out) and os.path.getsize(out)>1000: skip+=1; continue
    t=out+'.dl'
    r=subprocess.run(['curl','-sS','--cacert',CA,'-o',t,'--retry','3','--retry-delay','2',x['url']])
    if r.returncode or not os.path.exists(t) or os.path.getsize(t)<1000: bad.append((x['ep'],x['key'])); continue
    c=subprocess.run(['ffmpeg','-y','-loglevel','error','-i',t,'-ac','1','-ar','44100',out],capture_output=True)
    os.remove(t)
    if c.returncode: bad.append((x['ep'],x['key'])); continue
    got+=1
print(f'fetched {got}, already had {skip}, failed {len(bad)}', bad[:8])
