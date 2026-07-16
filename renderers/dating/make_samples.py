import json, os, re, subprocess, textwrap, urllib.request
from PIL import Image, ImageDraw, ImageFont

def load(p=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for l in open(p):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
K=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip().strip('"')
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"; H={"apikey":K,"Authorization":"Bearer "+K}
FF="/opt/homebrew/bin/ffmpeg"; FP="/opt/homebrew/bin/ffprobe"
FONT="scripts/TikTokSans36pt-ExtraBold.ttf"

SAMPLES=[(62,"v1"),(123,"v1"),(134,"v1")]   # 5s / 46s / 61s
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(62,123,134)&select=id,transcript,clip_text,text_hook_content,generated_text_hooks",headers=H)))
info={r["id"]:r for r in rows}

def hook_png(text,W,H_,path):
    clean=re.sub(r"\s+"," ",text or "").strip()
    if not clean: return False
    lines=textwrap.wrap(clean,width=28)
    fs=int(W*{1:0.062,2:0.058,3:0.052}.get(len(lines),0.046))
    font=ImageFont.truetype(FONT,fs)
    img=Image.new("RGBA",(W,H_),(0,0,0,0)); d=ImageDraw.Draw(img)
    lh=fs+int(fs*0.22); y=int(H_*0.07); stroke=max(3,fs//9)
    for i,ln in enumerate(lines):
        tw=d.textlength(ln,font=font); x=(W-tw)/2; yy=y+i*lh
        d.text((x,yy+3),ln,font=font,fill=(0,0,0,115))
        d.text((x,yy),ln,font=font,fill=(255,255,255,255),stroke_width=stroke,stroke_fill=(0,0,0,255))
    img.save(path); return True

for sid,ver in SAMPLES:
    r=info[sid]
    tr=(r.get("transcript") or r.get("clip_text") or "").replace("\n"," ")[:400]
    body=f"samples/_body_{sid}.mp4"
    rc=subprocess.run(["./.venv/bin/python3","scripts/run_pipeline.py",
        "--source",f"variants/dr_{sid}_{ver}.mp4","--reaction","assets/char3_talking.mp4",
        "--cutout","assets/char3_cutout.webm","--out",body,
        "--transcript",tr,"--hook-dur","1.8"],capture_output=True,text=True)
    if rc.returncode!=0: print(f"{sid} RENDER FAIL:",rc.stderr[-200:]); continue
    hooks=[h.get("text") for h in (r.get("generated_text_hooks") or []) if h.get("text")]
    top=r.get("text_hook_content") or (hooks[0] if hooks else "")
    probe=json.loads(subprocess.run([FP,"-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",body],capture_output=True,text=True).stdout)
    W,H_=probe["streams"][0]["width"],probe["streams"][0]["height"]
    png=f"samples/_h{sid}.png"; out=f"samples/SAMPLE-DR-{sid:03d}-{ver}.mp4"
    if hook_png(top,W,H_,png):
        subprocess.run([FF,"-y","-loglevel","error","-i",body,"-i",png,
            "-filter_complex","[0:v][1:v]overlay=0:0:enable='between(t,0,1.8)'[v]",
            "-map","[v]","-map","0:a","-c:v","libx264","-preset","veryfast","-crf","19",
            "-pix_fmt","yuv420p","-c:a","copy",out],check=True)
        os.remove(png)
    else:
        os.rename(body,out)
    if os.path.exists(body): os.remove(body)
    print(f"SAMPLE ready: {out}  hook={top[:50]!r}")
print("done")
