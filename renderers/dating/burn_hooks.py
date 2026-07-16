import json, os, re, subprocess, textwrap, glob, urllib.request
from PIL import Image, ImageDraw, ImageFont

def load(p=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for l in open(p):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
K=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip().strip('"')
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
FF="/opt/homebrew/bin/ffmpeg"; FP="/opt/homebrew/bin/ffprobe"
FONT="scripts/TikTokSans36pt-ExtraBold.ttf"
HOOK_DUR=1.8

rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=gte.60&select=id,text_hook_content,generated_text_hooks",
    headers={"apikey":K,"Authorization":"Bearer "+K})))
hooks={}
for r in rows:
    arr=[h.get("text","") for h in (r.get("generated_text_hooks") or []) if h.get("text")]
    top=r.get("text_hook_content") or ""
    if top and top not in arr: arr.insert(0,top)
    hooks[r["id"]]=arr

def hook_png(text,W,H,path):
    clean=re.sub(r"\s+"," ",text or "").strip()
    if not clean: return False
    lines=textwrap.wrap(clean,width=28)
    fs=int(W*{1:0.062,2:0.058,3:0.052}.get(len(lines),0.046))
    font=ImageFont.truetype(FONT,fs)
    img=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(img)
    lh=fs+int(fs*0.22); y=int(H*0.07)
    stroke=max(3,fs//9)
    for i,ln in enumerate(lines):
        tw=d.textlength(ln,font=font); x=(W-tw)/2; yy=y+i*lh
        d.text((x,yy+3),ln,font=font,fill=(0,0,0,115))
        d.text((x,yy),ln,font=font,fill=(255,255,255,255),stroke_width=stroke,stroke_fill=(0,0,0,255))
    img.save(path); return True

done=skip=fail=0
for f in sorted(glob.glob("renders/DR-*.mp4")):
    base=os.path.basename(f)                      # DR-062-v1.mp4
    m=re.match(r"DR-(\d+)-v(\d)\.mp4",base)
    sid=int(m.group(1)); ver=int(m.group(2))
    CLEAN={64,123,128,130}   # text audit 2026-07-11: only these have no source text
    arr=hooks.get(sid,[]) if sid in CLEAN else []
    if not arr:
        import shutil; shutil.copy2(f,f"renders_hooked/{base}"); skip+=1; print(f"{base}: no burn (source has own hook) -> copied"); continue
    text=arr[(ver-1)%len(arr)]
    probe=json.loads(subprocess.run([FP,"-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",f],capture_output=True,text=True).stdout)
    W,H=probe["streams"][0]["width"],probe["streams"][0]["height"]
    png=f"renders_hooked/_{base}.png"
    if not hook_png(text,W,H,png): skip+=1; continue
    out=f"renders_hooked/{base}"
    rc=subprocess.run([FF,"-y","-loglevel","error","-i",f,"-i",png,
        "-filter_complex",f"[0:v][1:v]overlay=0:0:enable='between(t,0,{HOOK_DUR})'[v]",
        "-map","[v]","-map","0:a","-c:v","libx264","-preset","veryfast","-crf","19",
        "-pix_fmt","yuv420p","-c:a","copy",out]).returncode
    os.remove(png)
    if rc==0: done+=1; print(f"{base}: {text[:50]!r}")
    else: fail+=1; print(f"{base}: ENCODE FAILED")
print(f"DONE: {done} hooked, {skip} skipped (no hook), {fail} failed")
