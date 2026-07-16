import json, os, subprocess, urllib.request, urllib.parse, base64

def load(path=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for line in open(path):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
def unq(s): return (s or "").strip().strip('"').strip("'")
KEY=unq(os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY"))
OR=unq(os.environ.get("OPENROUTER_API_KEY"))
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":KEY,"Authorization":"Bearer "+KEY}
FF="/opt/homebrew/bin/ffmpeg"
BASE=os.path.expanduser("~/Claude/dating-reaction")
CACHE=os.path.join(BASE,"cache"); VAR=os.path.join(BASE,"variants")

IDS=[60,62,64,70,104,110,111,113,115,117,119,120,123,125,128,129,130,131,132,133,134]
THREE_VARIANT_IDS=set(IDS[:8])   # 8 clips x3 + 13 clips x2 = 50

rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,url,handle"%",".join(map(str,IDS)),headers=H)))

def detect_text(path,sid):
    """3x3 montage -> Gemini: does the clip have burned-in text? Conservative: True on failure."""
    try:
        png=os.path.join(CACHE,f"textprobe_{sid}.png")
        dur=float(subprocess.run(["/opt/homebrew/bin/ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path],capture_output=True,text=True).stdout.strip() or 10)
        fps=max(0.1,round(9/min(dur,60),3))
        subprocess.run([FF,"-y","-loglevel","error","-t","60","-i",path,"-vf",f"fps={fps},scale=240:-1,tile=3x3","-frames:v","1",png],check=True)
        b64=base64.b64encode(open(png,"rb").read()).decode()
        body={"model":"google/gemini-2.5-flash","reasoning":{"enabled":False},"temperature":0,"max_tokens":60,
              "messages":[{"role":"user","content":[
                {"type":"text","text":"3x3 montage of video frames. Does the video have burned-in on-screen TEXT or CAPTIONS overlaid on the footage? Ignore watermarks/usernames/logos and scene text (signs, shirts). Reply ONLY JSON: {\"has_text\": true|false}"},
                {"type":"image_url","image_url":{"url":"data:image/png;base64,"+b64}}]}]}
        req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps(body).encode(),method="POST",
            headers={"Authorization":"Bearer "+OR,"Content-Type":"application/json"})
        txt=json.load(urllib.request.urlopen(req,timeout=60))["choices"][0]["message"]["content"]
        if isinstance(txt,list): txt=" ".join(p.get("text","") for p in txt)
        i,j=txt.find("{"),txt.rfind("}")
        return bool(json.loads(txt[i:j+1]).get("has_text",True))
    except Exception as e:
        print(f"  [text-detect fail id={sid}: {e} -> assume text, no flip]")
        return True

# Variant recipes: 5% edge crop (to 95%, slight per-version offset), light color grade, flip where safe.
# crop x/y offsets bias which edge loses more; grades are deliberately subtle.
RECIPES=[
    {"tag":"v1","ox":0.30,"oy":0.50,"eq":"eq=contrast=1.03:saturation=1.05","flip":False},
    {"tag":"v2","ox":0.70,"oy":0.50,"eq":"eq=brightness=0.015:saturation=0.94:gamma=1.02","flip":True},
    {"tag":"v3","ox":0.50,"oy":0.30,"eq":"eq=contrast=1.05:saturation=1.02:gamma=0.99","flip":False},
]

report=[]
for r in rows:
    sid=r["id"]; url=r["url"]
    src=os.path.join(CACHE,f"dr_{sid}.mp4")
    if not (os.path.exists(src) and os.path.getsize(src)>0):
        rc=subprocess.run(["yt-dlp","-q","--no-warnings","-f","mp4","-o",src,url]).returncode
        if rc!=0 or not os.path.exists(src):
            print(f"id={sid} DOWNLOAD FAILED"); report.append((sid,"download_failed",0)); continue
    has_text=detect_text(src,sid)
    n=3 if sid in THREE_VARIANT_IDS else 2
    made=0
    for rec in RECIPES[:n]:
        out=os.path.join(VAR,f"dr_{sid}_{rec['tag']}.mp4")
        flip="hflip," if (rec["flip"] and not has_text) else ""
        vf=(f"{flip}crop=floor(iw*0.95/2)*2:floor(ih*0.95/2)*2:floor((iw-floor(iw*0.95/2)*2)*{rec['ox']}):floor((ih-floor(ih*0.95/2)*2)*{rec['oy']}),"
            f"scale=iw:ih,{rec['eq']}")
        rc=subprocess.run([FF,"-y","-loglevel","error","-i",src,"-vf",vf,
            "-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","128k",out]).returncode
        if rc==0: made+=1
        else: print(f"id={sid} {rec['tag']} ENCODE FAILED")
    report.append((sid,"text" if has_text else "clean",made))
    print(f"id={sid} @{r['handle']}: {'has text (no flip)' if has_text else 'clean (v2 flipped)'} -> {made} variants")

total=sum(m for _,_,m in report)
print(f"DONE variants: {total} files from {len(report)} clips")
