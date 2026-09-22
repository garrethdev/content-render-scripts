"""Prepare the 4 voice reads (hook / story / turn / closer) for a batch-3 episode from its script beats.
- turn_at = index of the first body beat (from the 3rd on) that carries the burial/villain turn, so the
  house "hum before the villain beat" lands in the right place; falls back to the 60% mark.
- Numbers are spelled out for the voice clone (tts_prep.spoken).
Writes <out_dir>/<content_id>.reads.json = {"turn_at":n, "reads":{"hook":..,"story":..,"turn":..,"closer":..}}
Usage: python3 b3_tts_prep.py <out_dir> <content_id> [<content_id> ...]
"""
import sys, json, re, subprocess
sys.path.insert(0,'/home/user/calesthio/openmontage/projects/cleora-batch')
from tts_prep import spoken
KEY=os.environ.get('SUPABASE_KEY',''); CA='/root/.ccr/ca-bundle.crt'
URL='https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'
TURN=re.compile(r"\b(patent|patented|sold|profit|dollar|billion|million|company|companies|credit|his own name|renamed|ignored|denied|refused|dismissed|destroyed|banned|shelved|buried|prescrib|mocked|fired|erased|stole|stolen|took the|monopol|lobby|business|market)\w*", re.I)
out_dir=sys.argv[1]
for cid in sys.argv[2:]:
    r=subprocess.run(['curl','-s','--cacert',CA,f'{URL}?content_id=eq.{cid}&select=content_id,script,script_status','-H',f'apikey: {KEY}','-H',f'Authorization: Bearer {KEY}'],capture_output=True,text=True)
    row=json.loads(r.stdout)[0]; beats=row['script']['beats']; body=[b['vo'] for b in beats if b['slot'] in ('body','verdict')]  # verdict is spoken too
    turn_at=None
    for i,vo in enumerate(body):
        if i>=3 and TURN.search(vo): turn_at=i; break
    if turn_at is None or turn_at>=len(body)-1: turn_at=max(1,int(len(body)*0.6))
    reads={'hook':spoken(beats[0]['vo']),'story':spoken(' '.join(body[:turn_at])),'turn':spoken(' '.join(body[turn_at:])),'closer':spoken(beats[-1]['vo'])}
    json.dump({'content_id':cid,'turn_at':turn_at,'reads':reads},open(f'{out_dir}/{cid}.reads.json','w'),indent=1)
    print(f"{cid} ({row['script_status']}): body {len(body)} beats, turn_at={turn_at}; words hook/story/turn/closer = {[len(reads[k].split()) for k in ('hook','story','turn','closer')]}")
    print('   hook:', reads['hook'])
