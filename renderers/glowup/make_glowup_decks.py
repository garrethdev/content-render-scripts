#!/usr/bin/env python3
"""Feature+solution deck generator/renderer for the glow-up pipeline.
Reads glowup_decks copy, builds the 7-slide feature+solution manifest
(cover quad, before+2023, face/stomach/waist tips with diagonal 2+2 pairing,
peptide+quiz, after+2026), renders locally, uploads to glowup-renders,
sets suggested_sound + render_status='rendered'.
"""
import os, io, sys, json, random, urllib.request, urllib.parse
from PIL import Image, ImageDraw, ImageFont

REF="qlcmgxgwpzmiebzxflai"; KEY=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"]
REST=f"https://{REF}.supabase.co/rest/v1"; STOR=f"https://{REF}.supabase.co/storage/v1"
PUB=f"{STOR}/object/public/glowup-image-bank/"; HDR={"apikey":KEY,"Authorization":f"Bearer {KEY}"}
FONT="/System/Library/Fonts/Supplemental/Arial Bold.ttf"; OUT=os.path.expanduser("~/Claude/glowup-render/out2")
W,H=1080,1440
AFTER="honestly the peptide was the cheat code. it helped me keep the weight off. But I wouldn't change a thing.."
QUIZ_CTA='comment "QUIZ" and I\'ll send you the link'
FACE_TIPS=["depuff your face with lemon water","less puffy face in days? lemon water","debloat your face with cucumber water","snatched face starts with lemon water"]
STOM_TIPS=["flatter stomach? eat your protein first","flat tummy starts with protein not cardio","protein first and the bloat goes down","eat protein first for a flatter stomach"]
WAIST_TIPS=["snatched waist from 10k steps a day","snatch your waist just by walking daily","walk 10k steps for a smaller waist","a snatched waist from daily walks"]

def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=HDR),timeout=60))
def patch(dk,fields):
    urllib.request.urlopen(urllib.request.Request(f"{REST}/glowup_decks?deck_key=eq.{urllib.parse.quote(dk)}",
        data=json.dumps(fields).encode(),method="PATCH",headers={**HDR,"Content-Type":"application/json","Prefer":"return=minimal"}),timeout=60).read()

_cache={}
def fetch(path):
    if path in _cache: return _cache[path]
    d=urllib.request.urlopen(urllib.request.Request(PUB+urllib.parse.quote(path),headers={"User-Agent":"g"}),timeout=60).read()
    im=Image.open(io.BytesIO(d)).convert("RGB"); _cache[path]=im; return im

def fill(im,box):
    tw,th=box; r=max(tw/im.width,th/im.height); im=im.resize((int(im.width*r),int(im.height*r)))
    x=(im.width-tw)//2; y=(im.height-th)//2; return im.crop((x,y,x+tw,y+th))
def wrap(d,t,f,mw):
    ls=[]; cur=""
    for w in t.split():
        s=(cur+" "+w).strip()
        if d.textlength(s,font=f)<=mw: cur=s
        else: ls.append(cur); cur=w
    if cur: ls.append(cur)
    return ls
def cap(im,t,sz,yc=0.5):
    d=ImageDraw.Draw(im); f=ImageFont.truetype(FONT,sz); ls=wrap(d,t,f,W*0.86); lh=sz*1.2; y=H*yc-lh*len(ls)/2
    for ln in ls:
        x=(W-d.textlength(ln,font=f))/2
        d.text((x+2,y+3),ln,font=f,fill=(0,0,0)); d.text((x,y),ln,font=f,fill=(255,255,255),stroke_width=3,stroke_fill=(0,0,0)); y+=lh
    return im
def datestamp(im,month,yr):  # month over year, top-right. replaces the old BEFORE/AFTER tag
    d=ImageDraw.Draw(im); f=ImageFont.truetype(FONT,60)
    for i,txt in enumerate((month,yr)):
        tw=d.textlength(txt,font=f); x=W-tw-46; y=40+i*66
        d.text((x+2,y+3),txt,font=f,fill=(0,0,0))
        d.text((x,y),txt,font=f,fill=(255,255,255),stroke_width=3,stroke_fill=(0,0,0))
    return im
MONTHS=["January","February","March","April","May","June","July","August","September","October","November","December"]
def quad(paths):
    c=Image.new("RGB",(W,H),(12,10,9))
    for p,(x,y) in zip(paths,[(0,0),(W//2,0),(0,H//2),(W//2,H//2)]): c.paste(fill(fetch(p),(W//2,H//2)),(x,y))
    return c
def single(p): return fill(fetch(p),(W,H))

_lum={}
def lum(path):
    """Mean luminance 0-255 of a bank image. Measured, not read from the bank's
    `brightness` column — that column is null on 6 of 8 face images and a wrong tag
    is worse than no tag."""
    if path not in _lum:
        im=fetch(path).convert("L").resize((32,32))
        px=list(im.getdata()); _lum[path]=sum(px)/len(px)
    return _lum[path]

def _p(c): return c[1] if isinstance(c,tuple) else c

def matched_pair(cands, keyfn=None, tol=40):
    """Two cells whose LIGHTING matches — a diagonal must never put a near-black cell
    opposite a white one. Brightness is the hard rule; category variety is only a
    tiebreak among cells that already match. (Forcing different categories first put a
    black air-bike opposite a white tape measure, because `measure` has one bright image.)
    Random anchor keeps variety across decks."""
    if len(cands)<2: return (cands*2)[:2]
    a=random.choice(cands); la=lum(_p(a))
    others=[c for c in cands if c!=a]
    close=[c for c in others if abs(lum(_p(c))-la)<=tol]
    if not close:                       # nothing matches: take the nearest anyway
        return (a, min(others,key=lambda c: abs(lum(_p(c))-la)))
    if keyfn:
        diff=[c for c in close if keyfn(c)!=keyfn(a)]
        if diff: return (a, random.choice(diff))
    return (a, random.choice(close))

def upload(dk,n,im):
    buf=io.BytesIO(); im.save(buf,"PNG"); buf.seek(0)
    urllib.request.urlopen(urllib.request.Request(f"{STOR}/object/glowup-renders/{dk}/slide{n}.png",
        data=buf.read(),method="POST",headers={**HDR,"Content-Type":"image/png","x-upsert":"true"}),timeout=120).read()

def main():
    bank=get(f"{REST}/glowup_image_bank?status=eq.active&select=pool,category,label,storage_path")
    def cells(pool,cats=None,exclude=None,withcat=False):
        r=[((b["category"],b["storage_path"]) if withcat else b["storage_path"])
           for b in bank if b["pool"]==pool and (cats is None or b["category"] in cats) and (exclude is None or exclude not in b["label"])]
        return r
    covers=cells("cover"); befores=cells("before"); afters=cells("after"); quizc=cells("quiz")
    # slide 2 draws a regular portrait rather than the staged "before" pool
    regulars=cells("cover") or befores
    # res = the ONE woman-with-product cell per middle slide (kept minimal so the deck's only
    # real "characters" are the before/after woman). sol = the product/solution cells (the focus).
    face_res=cells("feature",["face"])
    stom_res=cells("feature",["stomach"])+cells("body",["abs"])
    waist_res=cells("feature",["waist"])+cells("body",["gym"])
    water_sol=cells("evidence",["water","facetool"],exclude="lemonwater_bw",withcat=True)
    prot_sol=cells("evidence",["protein","eggs","greens","meal_prep"],withcat=True)
    step_sol=cells("evidence",["steps","measure"],withcat=True)
    sounds=[s for s in get(f"{REST}/music_library?select=artist,title,same_style_url,pillar_fit,genre&is_active=eq.true")
            if "glowup_carousel" in (s.get("pillar_fit") or [])]
    def pair(res,sol):
        """maxxingnation 2x2 rule (maxxingnation-research/FACT_BANK.md):
        2 evidence cells + 2 body/person cells. The two evidence cells are drawn from
        DIFFERENT categories so a narrow pool can never fill a slide with three
        near-identical props (the 3-lemon-waters bug). sol is [(category,path)]."""
        # evidence: 2 cells, DIFFERENT categories, MATCHED lighting
        ea,eb=matched_pair(sol, keyfn=lambda c: c[0])
        ev=[ea[1],eb[1]]
        # body: 2 cells, matched lighting to each other
        bodies=list(matched_pair(res))
        # DIAGONAL placement. quad() pastes TL,TR,BL,BR — a matching pair must land on a
        # diagonal (TL+BR and TR+BL), never as a top row and a bottom row.
        (b0,b1),(e0,e1)=bodies,ev
        return [b0,e0,e1,b1] if random.random()<0.5 else [e0,b0,b1,e1]
    def sound_for(hook):
        emo=any(k in hook.lower() for k in ["breakup","rejection","divorce","kids","aura","invisible","hiding","hated","believing","losing your","gave up"])
        pool=[s for s in sounds if ("sade" in (s["artist"] or "").lower())==emo] or sounds
        s=random.choice(pool) if pool else None
        return (s["artist"]+" - "+s["title"]+(" | "+s["same_style_url"] if s.get("same_style_url") else "")) if s else ""

    # Optional argv PostgREST filters (e.g. "render_status=eq.pending" "batch=eq.X").
    # Default = UNRENDERED rows only (forward-looking; never re-touches rendered decks).
    # Pass --all for the legacy render-everything behavior.
    args=[a for a in sys.argv[1:] if a!="--all"]
    q="".join("&"+f for f in args)
    if "--all" not in sys.argv[1:] and not any(a.startswith("render_status") for a in args):
        q+="&or=(render_status.is.null,render_status.eq.pending)"
    decks=get(f"{REST}/glowup_decks?select=*&order=id{q}")
    print(f"{len(decks)} decks")
    for k,deck in enumerate(decks):
        dk=deck["deck_key"]; hook=deck["hook"]; random.seed(dk)
        slides=[
            cap(quad(random.sample(covers,4)),hook,56),
            # slide 2: normal slide, no datestamp. only the final reveal carries a date.
            cap(single(random.choice(regulars)),deck["before_line"],48),
            cap(quad(pair(face_res,water_sol)),deck.get("tip_face") or random.choice(FACE_TIPS),50),
            cap(quad(pair(stom_res,prot_sol)),deck.get("tip_stomach") or random.choice(STOM_TIPS),48),
            cap(cap(single(random.choice(quizc)),deck["quiz_line"],44,0.13),QUIZ_CTA,40,0.9),
            cap(quad(pair(waist_res,step_sol)),deck.get("tip_waist") or random.choice(WAIST_TIPS),50),
            datestamp(cap(single(random.choice(afters)),AFTER,42),"July","2026"),
        ]
        d=f"{OUT}/{dk}"; os.makedirs(d,exist_ok=True)
        for i,im in enumerate(slides,1): im.save(f"{d}/slide{i}.png"); upload(dk,i,im)
        urls={f"slide_{i}_url": f"{STOR}/object/public/glowup-renders/{dk}/slide{i}.png" for i in range(1,8)}
        patch(dk,{**urls,"render_status":"rendered","suggested_sound":sound_for(hook),"after_line":AFTER})
        print(f"  [{k+1}/{len(decks)}] {dk[:22]} :: {hook[:34]}")
    print("done")

if __name__=="__main__": main()
