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
def year(im,yr):
    d=ImageDraw.Draw(im); f=ImageFont.truetype(FONT,64); tw=d.textlength(yr,font=f); x=W-tw-46
    d.text((x+2,43),yr,font=f,fill=(0,0,0)); d.text((x,40),yr,font=f,fill=(255,255,255),stroke_width=3,stroke_fill=(0,0,0)); return im
def tag(im,text):  # bold BEFORE/AFTER label, top-left corner
    d=ImageDraw.Draw(im); f=ImageFont.truetype(FONT,58)
    d.text((48,42),text,font=f,fill=(0,0,0)); d.text((46,40),text,font=f,fill=(255,255,255),stroke_width=3,stroke_fill=(0,0,0)); return im
def quad(paths):
    c=Image.new("RGB",(W,H),(12,10,9))
    for p,(x,y) in zip(paths,[(0,0),(W//2,0),(0,H//2),(W//2,H//2)]): c.paste(fill(fetch(p),(W//2,H//2)),(x,y))
    return c
def single(p): return fill(fetch(p),(W,H))

def upload(dk,n,im):
    buf=io.BytesIO(); im.save(buf,"PNG"); buf.seek(0)
    urllib.request.urlopen(urllib.request.Request(f"{STOR}/object/glowup-renders/{dk}/slide{n}.png",
        data=buf.read(),method="POST",headers={**HDR,"Content-Type":"image/png","x-upsert":"true"}),timeout=120).read()

def main():
    bank=get(f"{REST}/glowup_image_bank?status=eq.active&select=pool,category,label,storage_path")
    def cells(pool,cats=None,exclude=None):
        r=[b["storage_path"] for b in bank if b["pool"]==pool and (cats is None or b["category"] in cats) and (exclude is None or exclude not in b["label"])]
        return r
    covers=cells("cover"); befores=cells("before"); afters=cells("after"); quizc=cells("quiz")
    # res = the ONE woman-with-product cell per middle slide (kept minimal so the deck's only
    # real "characters" are the before/after woman). sol = the product/solution cells (the focus).
    face_res=cells("feature",["face"])
    stom_res=cells("feature",["stomach"])+cells("body",["abs"])
    waist_res=cells("feature",["waist"])+cells("body",["gym"])
    water_sol=cells("evidence",["water","facetool"],exclude="lemonwater_bw")
    prot_sol=cells("evidence",["protein","eggs","greens","meal_prep"])
    step_sol=cells("evidence",["steps"])
    sounds=[s for s in get(f"{REST}/music_library?select=artist,title,same_style_url,pillar_fit,genre&is_active=eq.true")
            if "glowup_carousel" in (s.get("pillar_fit") or [])]
    def pair(res,sol):  # product-heavy 2x2: 3 product cells + 1 woman-with-product
        s=random.sample(sol,3) if len(sol)>=3 else (sol*3)[:3]
        cells=list(s)
        if res:
            cells.insert(random.randint(0,3), random.choice(res))  # woman at a random corner
        else:
            cells.append(random.choice(sol))  # no woman-with-product yet -> 4 products
        return cells[:4]
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
            tag(year(cap(single(random.choice(befores)),deck["before_line"],48),"2023"),"BEFORE"),
            cap(quad(pair(face_res,water_sol)),deck.get("tip_face") or random.choice(FACE_TIPS),50),
            cap(quad(pair(stom_res,prot_sol)),deck.get("tip_stomach") or random.choice(STOM_TIPS),48),
            cap(cap(single(random.choice(quizc)),deck["quiz_line"],44,0.13),QUIZ_CTA,40,0.9),
            cap(quad(pair(waist_res,step_sol)),deck.get("tip_waist") or random.choice(WAIST_TIPS),50),
            tag(year(cap(single(random.choice(afters)),AFTER,42),"2026"),"AFTER"),
        ]
        d=f"{OUT}/{dk}"; os.makedirs(d,exist_ok=True)
        for i,im in enumerate(slides,1): im.save(f"{d}/slide{i}.png"); upload(dk,i,im)
        patch(dk,{"render_status":"rendered","suggested_sound":sound_for(hook),"after_line":AFTER})
        print(f"  [{k+1}/{len(decks)}] {dk[:22]} :: {hook[:34]}")
    print("done")

if __name__=="__main__": main()
