import json, os, base64, subprocess, urllib.request

def load(p=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for l in open(p):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
def unq(s): return (s or "").strip().strip('"').strip("'")
K=unq(os.environ["CAROUSEL_SUPABASE_SECRET_KEY"])
OR=unq(os.environ["OPENROUTER_API_KEY"])
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":K,"Authorization":"Bearer "+K,"Content-Type":"application/json"}
FF="/opt/homebrew/bin/ffmpeg"; FP="/opt/homebrew/bin/ffprobe"
CACHE="cache"

IDS=[60,62,64,70,104,110,111,113,115,117,119,120,123,125,128,129,130,131,132,133,134]

PROMPT=("You are auditing a TikTok clip for burned-in text. Image 1 is a 3x3 montage of the FIRST 4 SECONDS "
"(read left to right); image 2 is a 3x3 montage of the WHOLE clip. Identify every piece of text OVERLAID on the "
"footage (ignore watermarks, usernames, and text physically in the scene). Reply ONLY JSON:\n"
"{\"has_text\": true|false, \"zones\": [\"top\"|\"middle\"|\"bottom\"], "
"\"has_creator_hook\": true|false,  // a title/hook-style text block, usually top or upper area, present from the first frames\n"
"\"hook_zone\": \"top\"|\"middle\"|\"bottom\"|null, \"hook_text\": \"...or null\", "
"\"has_subtitles\": true|false }  // word-by-word or line captions that change with speech")

def montage(src,out,t0,t1):
    dur=max(0.5,t1-t0); fps=max(0.1,round(9/dur,3))
    subprocess.run([FF,"-y","-loglevel","error","-ss",str(t0),"-t",str(dur),"-i",src,
        "-vf",f"fps={fps},scale=360:-1,tile=3x3","-frames:v","1",out],check=True)

def gem(images,prompt):
    content=[{"type":"text","text":prompt}]
    for p in images:
        b64=base64.b64encode(open(p,"rb").read()).decode()
        content.append({"type":"image_url","image_url":{"url":"data:image/png;base64,"+b64}})
    body={"model":"google/gemini-2.5-flash","reasoning":{"enabled":False},"temperature":0,"max_tokens":300,
          "messages":[{"role":"user","content":content}]}
    req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps(body).encode(),
        method="POST",headers={"Authorization":"Bearer "+OR,"Content-Type":"application/json"})
    txt=json.load(urllib.request.urlopen(req,timeout=90))["choices"][0]["message"]["content"]
    if isinstance(txt,list): txt=" ".join(p.get("text","") for p in txt if isinstance(p,dict))
    i,j=txt.find("{"),txt.rfind("}")
    return json.loads(txt[i:j+1])

results=[]
for sid in IDS:
    src=os.path.join(CACHE,f"dr_{sid}.mp4")
    if not os.path.exists(src): print(f"id={sid} no cache, skip"); continue
    dur=float(subprocess.run([FP,"-v","error","-show_entries","format=duration","-of","csv=p=0",src],capture_output=True,text=True).stdout.strip() or 10)
    m1=f"{CACHE}/audit_first_{sid}.png"; m2=f"{CACHE}/audit_full_{sid}.png"
    try:
        montage(src,m1,0,min(4,dur)); montage(src,m2,0,min(60,dur))
        d=gem([m1,m2],PROMPT)
        row={"id":sid,**{k:d.get(k) for k in ("has_text","zones","has_creator_hook","hook_zone","hook_text","has_subtitles")}}
        results.append(row)
        urllib.request.urlopen(urllib.request.Request(
            SB+f"/rest/v1/dating_reaction_sources?id=eq.{sid}",
            data=json.dumps({"has_text_hook":bool(d.get("has_creator_hook")),
                             "original_text_hook":(d.get("hook_text") or None),
                             "text_hook_placement":(d.get("hook_zone") or None)}).encode(),
            method="PATCH",headers={**H,"Prefer":"return=minimal"}))
        print(json.dumps(row))
    except Exception as e:
        print(f"id={sid} AUDIT FAILED: {e}")
print("AUDIT DONE:",len(results),"clips")
