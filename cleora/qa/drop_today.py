"""Remove the TODAY / product-pivot section from the slate.

The owner: "remove the whole backdrop of forbidden fruit and peptides, that whole section doesn't work
yet - just get the initial story down." So every beat with kind='today' comes out, plus the one legacy
closer that pivots to peptides.

The matching EDL cut is removed at the same index rather than re-running the Director: each remaining
clip was chosen for the beat it still sits on, so the casting stays valid and the episode does not need
a re-cast (the Director is down on its credential anyway). Removing beats can leave two identical clips
adjacent, which R7 forbids, so that is checked and repaired from the episode's own unused pool.

Usage: python3 slate/drop_today.py [--apply]
"""
import json, re, subprocess, sys
K=os.environ.get('SUPABASE_KEY',''); CA='/root/.ccr/ca-bundle.crt'
U='https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'
H=['-H',f'apikey: {K}','-H',f'Authorization: Bearer {K}','-H','Content-Type: application/json']
PEPTIDE=re.compile(r'forbidden fruit|peptides have been studied', re.I)
wc=lambda s: len(re.findall(r"[A-Za-z0-9']+", s))

lib=json.loads(subprocess.run(['curl','-s','--cacert',CA,
    f'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_clips?status=eq.active&vo_safe=eq.true&select=shot_key,video_public_url']+H,
    capture_output=True,text=True).stdout)
VO={c['shot_key']:c['video_public_url'] for c in lib}

ids=[r['id'] for r in json.load(open('/home/user/carousel-agent/cleora/review48/data48.json'))]
apply='--apply' in sys.argv
tot_b=tot_c=tot_fix=0; touched=0
for cid in ids:
    row=json.loads(subprocess.run(['curl','-s','--cacert',CA,
        f'{U}?content_id=eq.{cid}&select=script,edl']+H,capture_output=True,text=True).stdout)[0]
    beats=row['script']['beats']; cuts=(row.get('edl') or {}).get('cuts') or []
    aligned = len(cuts)==len(beats)
    drop=set()
    for i,b in enumerate(beats):
        if (b.get('kind')=='today') or (i==len(beats)-1 and PEPTIDE.search(b['vo'])): drop.add(i)
    # never drop the last beat without promoting a replacement closer
    if len(beats)-1 in drop:
        keep=[i for i in range(len(beats)) if i not in drop]
        if not keep: continue
        beats[keep[-1]]['slot']='closer'
    nb=[b for i,b in enumerate(beats) if i not in drop]
    nc=[c for i,c in enumerate(cuts) if i not in drop] if aligned else cuts
    if aligned and nc: nc[-1]['slot']='closer'
    # R7: removing beats can butt two identical clips together
    fixes=0
    if aligned:
        used={c['clip_key'] for c in nc}
        for i in range(1,len(nc)):
            if nc[i]['clip_key'] and nc[i]['clip_key']==nc[i-1]['clip_key']:
                prev=nc[i-1]['clip_key']; nxt=nc[i+1]['clip_key'] if i+1<len(nc) else None
                alt=next((k for k in VO if k not in used and k!=prev and k!=nxt and not k.startswith('cleora_')), None)
                if alt: nc[i]['clip_key']=alt; nc[i]['url']=VO[alt]; used.add(alt); fixes+=1
    if not drop: continue
    touched+=1; tot_b+=len(drop); tot_c+=(len(cuts)-len(nc)); tot_fix+=fixes
    print(f'{cid}: {len(beats)}->{len(nb)} beats, {len(cuts)}->{len(nc)} cuts'
          + (f', {fixes} adjacency fix(es)' if fixes else '')
          + ('' if aligned else '  [EDL was already out of step - cuts left alone]'))
    if apply:
        sc=dict(row['script']); sc['beats']=nb; sc['words']=sum(wc(b['vo']) for b in nb)
        sc['source']=(sc.get('source') or '')+' + today section removed'
        body={'script':sc,'notes':'TODAY/product section removed - story only'}
        if aligned:
            edl=dict(row['edl']); edl['cuts']=nc; body['edl']=edl
        p='/tmp/_dt.json'; json.dump(body,open(p,'w'))
        subprocess.run(['curl','-s','-o','/dev/null','--cacert',CA,'-X','PATCH',f'{U}?content_id=eq.{cid}']+H+
                       ['-H','Prefer: return=minimal','--data-binary',f'@{p}'],capture_output=True)
print(f'\n{touched} episodes, {tot_b} beats removed, {tot_c} cuts removed, {tot_fix} adjacency repairs')
print('DRY RUN - pass --apply to write' if not apply else 'APPLIED')
