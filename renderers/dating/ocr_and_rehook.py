import json, os, time, base64, subprocess, urllib.request

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
H={"apikey":KEY,"Authorization":"Bearer "+KEY,"Content-Type":"application/json"}
FF="/opt/homebrew/bin/ffmpeg"
CACHE=os.path.expanduser("~/Claude/dating-reaction/cache")

IDS=[60,62,104,110,111,115,117,132,133]

def gem_vision(png,prompt):
    b64=base64.b64encode(open(png,"rb").read()).decode()
    body={"model":"google/gemini-2.5-flash","reasoning":{"enabled":False},"temperature":0,"max_tokens":400,
          "messages":[{"role":"user","content":[{"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":"data:image/png;base64,"+b64}}]}]}
    req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps(body).encode(),
        method="POST",headers={"Authorization":"Bearer "+OR,"Content-Type":"application/json"})
    txt=json.load(urllib.request.urlopen(req,timeout=90))["choices"][0]["message"]["content"]
    if isinstance(txt,list): txt=" ".join(p.get("text","") for p in txt)
    return txt

PROMPT=("This is a 3x3 frame montage of a short TikTok about dating (plus-size woman creator). "
"1) Read ALL burned-in on-screen text/captions you can see, in order. "
"2) In one line, state the specific dating complaint or situation shown. "
"Reply ONLY JSON: {\"onscreen_text\": \"...\", \"situation\": \"...\"}")

for sid in IDS:
    src=os.path.join(CACHE,f"dr_{sid}.mp4")
    png=os.path.join(CACHE,f"ocrprobe_{sid}.png")
    try:
        dur=float(subprocess.run(["/opt/homebrew/bin/ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",src],capture_output=True,text=True).stdout.strip() or 10)
        fps=max(0.1,round(9/min(dur,60),3))
        subprocess.run([FF,"-y","-loglevel","error","-t","60","-i",src,"-vf",f"fps={fps},scale=360:-1,tile=3x3","-frames:v","1",png],check=True)
        txt=gem_vision(png,PROMPT)
        i,j=txt.find("{"),txt.rfind("}")
        d=json.loads(txt[i:j+1])
        clip_text=(d.get("onscreen_text","")+" || SITUATION: "+d.get("situation","")).strip()
        urllib.request.urlopen(urllib.request.Request(
            SB+"/rest/v1/dating_reaction_sources?id=eq."+str(sid),
            data=json.dumps({"clip_text":clip_text[:900]}).encode(),method="PATCH",
            headers={**H,"Prefer":"return=minimal"}))
        print(f"id={sid}: {clip_text[:90]!r}")
    except Exception as e:
        print(f"id={sid} OCR FAILED: {e}")

time.sleep(2)
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,handle,complaint_flavor,clip_text,transcript,caption,text_hook_content"%",".join(map(str,IDS)),headers=H)))
print(f"\nre-hooking {len(rows)}")
for r in rows:
    r["text_hook_content"]=None
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://czed.app.n8n.cloud/webhook/dating-genre-hookmaker",
            data=json.dumps(r).encode(),method="POST",headers={"Content-Type":"application/json"}),timeout=180)
        print(f"id={r['id']} re-hooked")
    except Exception as e:
        print(f"id={r['id']} FAILED: {e}")
    time.sleep(20)
print("DONE")
