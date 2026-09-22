"""Split over-long body beats so no shot holds longer than ~5s.

The Director casts ONE clip per beat and the renderer holds that clip for as long as its beat is spoken,
so beat length IS shot length. Beats written as a single long evidence sentence ("In a 12-week trial of
50 women, ...") therefore freeze the picture for 9-14 seconds.

Split at the sentence boundary nearest the middle; when a beat is one long sentence, split at the
clause boundary (comma / semicolon / colon / dash) nearest the middle instead. Recursive, and each side
must keep >=5 words so we never make a flash beat.

TOKEN ORDER AND COUNT ARE PRESERVED - the concatenated body text is byte-identical, so voice reads
already generated from it stay valid; only the beat boundaries move.

Usage: python3 slate/resplit.py [--apply]
"""
import json,re,sys,subprocess
KEY=os.environ.get('SUPABASE_KEY',''); CA='/root/.ccr/ca-bundle.crt'
URL='https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'
H=['-H',f'apikey: {KEY}','-H',f'Authorization: Bearer {KEY}','-H','Content-Type: application/json']
MAXW=12                     # ~4.4s at Cleora's 2.7 words/sec
BODY={'body','verdict'}
def wc(s): return len(re.findall(r"[A-Za-z0-9']+", s))
def cap(s): return ' '.join(w for w in re.findall(r"[A-Za-z0-9']+", s) if len(w)>2)[:40].upper()
def _pieces(vo):
    s=[x for x in re.findall(r"[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$", vo) if x.strip()]
    if len(s)>=2: return s
    c=re.split(r'(?<=[,;:])\s+|\s+(?=[-–—]\s)', vo)   # clause fallback for one long sentence
    return [x for x in c if x.strip()] if len(c)>=2 else []
def split_long(b):
    if b['slot'] not in BODY or wc(b['vo'])<=MAXW: return [b]
    p=_pieces(b['vo'])
    if len(p)<2: return [b]
    tot=wc(b['vo']); acc=0; best=None
    for i in range(len(p)-1):
        acc+=wc(p[i]); d=abs(acc-tot/2)
        if best is None or d<best[0]: best=(d,i)
    i=best[1]; a=' '.join(''.join(p[:i+1]).split()); c=' '.join(''.join(p[i+1:]).split())
    if wc(a)<5 or wc(c)<5: return [b]
    ka={k:v for k,v in b.items() if k not in ('vo','caption')}
    return (split_long({**ka,'vo':a,'caption':b.get('caption') or cap(a)})
          + split_long({**ka,'vo':c,'caption':cap(c)}))
ids=[r['id'] for r in json.load(open('/home/user/carousel-agent/cleora/review48/data48.json'))]
todo=[]
for cid in ids:
    r=json.loads(subprocess.run(['curl','-s','--cacert',CA,
        f'{URL}?content_id=eq.{cid}&select=content_id,script,script_status']+H,capture_output=True,text=True).stdout)[0]
    s=r['script']; beats=s['beats']
    new=[x for b in beats for x in split_long(b)]
    if len(new)==len(beats): continue
    old_txt=' '.join(b['vo'] for b in beats); new_txt=' '.join(b['vo'] for b in new)
    assert re.findall(r"[A-Za-z0-9']+",old_txt)==re.findall(r"[A-Za-z0-9']+",new_txt), cid
    todo.append((cid,beats,new,s))
    print(f"{cid}: {len(beats)} -> {len(new)} beats; longest {max(wc(b['vo']) for b in beats)}w "
          f"-> {max(wc(b['vo']) for b in new)}w  ({max(wc(b['vo']) for b in beats)/2.7:.1f}s -> "
          f"{max(wc(b['vo']) for b in new)/2.7:.1f}s)")
print(len(todo),'of',len(ids),'episodes need re-splitting')
if '--apply' in sys.argv:
    for cid,old,new,s in todo:
        s2=dict(s); s2['beats']=new; s2['words']=sum(wc(b['vo']) for b in new)
        s2['source']=(s.get('source') or '')+f' + resplit>{MAXW}w'
        body=json.dumps({'script':s2,'script_status':'written',
                         'notes':f'beats re-split at <={MAXW}w so no shot holds past ~5s; re-cast'})
        p=subprocess.run(['curl','-s','--cacert',CA,'-X','PATCH',f'{URL}?content_id=eq.{cid}']+H+
                         ['-H','Prefer: return=minimal','-d',body],capture_output=True,text=True)
        print(' PATCH',cid,'ok' if not p.stdout.strip() else p.stdout[:120])
