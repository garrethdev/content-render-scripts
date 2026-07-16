"""Vetted re-render driver: pinned character, cover-first slide 1, 3 attempts,
verify-after (authoritative storage metadata: all slides written this run,
one character, slide1 is a cover), JSONL log."""
import json,urllib.request,time,random,sys,os,datetime
URL='https://carousel-command-center.vercel.app/api/render-carousel'
SVC=os.environ['CAROUSEL_SUPABASE_SECRET_KEY']
STORE='https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/list/carousel-renders'
SH={'apikey':SVC,'Authorization':'Bearer '+SVC,'Content-Type':'application/json'}
POOLS={  # pillar -> {character: pool_size} (verified against bucket 2026-07-02)
 'bw_gatekeeping':{'char2':20,'char2_before':7,'char3':10},
 'strong_informational':{'char2':20,'char2_before':7,'char3':10},
 'rich_life':{'char2':26,'char3':3},
}
def pin_character(pillar,n_slides,rng):
    # Auto-rotation excludes "_before" pools (heavier transformation-before era) —
    # those are opt-in for explicit before/after content, not random assignment.
    elig={c:n for c,n in POOLS[pillar].items() if n>=n_slides and not c.endswith('_before')}
    if not elig: elig={c:n for c,n in POOLS[pillar].items() if n>=n_slides}
    if not elig: elig=POOLS[pillar]
    chars,weights=zip(*elig.items())
    return rng.choices(chars,weights=weights)[0]  # proportional to pool size

def trim_orphans(cid,n_slides):
    # Delete any slide file beyond the content count (old CTA / stale slides that
    # the original 7-slide renders left behind), so the folder is exactly N slides.
    try:
        body=json.dumps({'prefix':cid+'/','limit':100}).encode()
        items=json.load(urllib.request.urlopen(
            urllib.request.Request(STORE,data=body,headers=SH,method='POST'),timeout=30))
        extra=[f"{cid}/{x['name']}" for x in items if x.get('id') and
               int(x['name'].replace('slide_','').replace('.jpg','')) > n_slides]
        if extra:
            urllib.request.urlopen(urllib.request.Request(
                'https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/carousel-renders',
                data=json.dumps({'prefixes':extra}).encode(),headers=SH,method='DELETE'),timeout=60)
        return len(extra)
    except Exception:
        return -1

def storage_check(cid,n_slides,run_start):
    # Authoritative: list the carousel folder via storage API and confirm exactly
    # the expected slides exist AND each was written this run (updated_at recent).
    # No CDN involved, so no false negatives from edge lag.
    try:
        body=json.dumps({'prefix':cid+'/','limit':100}).encode()
        items=json.load(urllib.request.urlopen(
            urllib.request.Request(STORE,data=body,headers=SH,method='POST'),timeout=30))
        files={x['name']:x for x in items if x.get('id')}
        expected=[f'slide_0{i}.jpg' for i in range(1,n_slides+1)]
        if sorted(files)!=sorted(expected):  # no orphans, no missing
            return False
        for name in expected:
            ts=datetime.datetime.fromisoformat(files[name]['updated_at'].replace('Z','+00:00')).timestamp()
            if ts < run_start-120: return False
        return True
    except Exception:
        return False

def run(rows_file,log_file,seed=42):
    rows=json.load(open(rows_file))
    rng=random.Random(seed)
    run_start=time.time()
    log=open(log_file,'a')
    ok=failed=0
    for n,r in enumerate(rows,1):
        texts={f'slide_{i}':r[f'slide_{i}'] for i in range(1,7) if r.get(f'slide_{i}') and str(r[f'slide_{i}']).strip()}
        char=pin_character(r['pillar'],len(texts),rng)
        body={'carousel_id':r['carousel_id'],'pillar':r['pillar'],'character':char,**texts}
        rec={'id':r['carousel_id'],'pillar':r['pillar'],'pinned':char,'slides':len(texts)}
        resp=None
        for attempt in (1,2,3):
            try:
                req=urllib.request.Request(URL,data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json'},method='POST')
                resp=json.load(urllib.request.urlopen(req,timeout=180))
                if 'error' in resp: raise RuntimeError(resp['error'])
                break
            except Exception as e:
                rec[f'attempt_{attempt}_error']=str(e)[:200]; resp=None; time.sleep(5*attempt)
        if resp:
            bgs=resp.get('bgs',[])
            folders={b.split('/')[2] for b in bgs}
            rec['trimmed']=trim_orphans(r['carousel_id'],len(bgs))
            verified=storage_check(r['carousel_id'],len(bgs),run_start)
            s1_cover=bool(bgs) and bgs[0].split('/')[-1].startswith('cover_')
            char_locked=len(folders)==1 and resp.get('character')==char
            rec.update({'status':'ok','character':resp.get('character'),
                        'distinct':len(set(bgs)),'n_bgs':len(bgs),
                        'folders':sorted(folders),'verified_fresh':verified,
                        'slide1_cover':s1_cover,'cover':resp.get('cover'),
                        'char_locked':char_locked})
            if verified and char_locked and s1_cover: ok+=1
            else: rec['status']='verify_failed'; failed+=1
        else:
            rec['status']='render_failed'; failed+=1
        log.write(json.dumps(rec)+'\n'); log.flush()
        print(f"[{n}/{len(rows)}] {rec['id']} {rec['status']} char={rec.get('character')} "
              f"s1cover={rec.get('slide1_cover')} distinct={rec.get('distinct')}/{rec.get('n_bgs')} fresh={rec.get('verified_fresh')}")
    print(f"\nRESULT ok={ok} failed={failed} of {len(rows)}")
    return failed

if __name__=='__main__':
    sys.exit(1 if run(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 42) else 0)
