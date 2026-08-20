#!/usr/bin/env python3
"""Screen REPLACEMENT candidates before spending any probe/render time on them.
Frames are pulled straight from Supabase storage over HTTP range requests (~2s each),
so nothing is downloaded in full until a candidate passes."""
import os, sys, json, subprocess, base64, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screen_bases import PROMPT, parse, MODEL

FF="/opt/homebrew/bin/ffmpeg"; FR="screen_frames"; os.makedirs(FR,exist_ok=True)
OUT="candidate_screen.json"

def frames(url, aid):
    out=[]
    for t in (0.3, 1.2, 2.4):
        p=os.path.join(FR,f"c{aid}_{t}.jpg")
        if not os.path.exists(p):
            r=subprocess.run([FF,"-y","-loglevel","error","-ss",str(t),"-i",url,"-frames:v","1",
                              "-vf","scale=600:-2","-q:v","3",p],capture_output=True,text=True)
            if r.returncode!=0 or not os.path.exists(p): return None
        out.append(p)
    return out

def screen(c):
    aid=str(c["aweme_id"])
    fs=frames(c["source_video_url"], aid)
    if not fs: return aid, {"error":"frame extract failed"}
    content=[{"type":"text","text":PROMPT}]
    for i,p in enumerate(fs,1):
        b=base64.b64encode(open(p,"rb").read()).decode()
        content+=[{"type":"text","text":f"Frame {i}:"},
                  {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}}]
    body={"model":MODEL,"messages":[{"role":"user","content":content}],"max_tokens":3000}
    req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization":"Bearer "+os.environ["OPENROUTER_API_KEY"],"Content-Type":"application/json"})
    for attempt in (1,2):
        try:
            j=json.load(urllib.request.urlopen(req,timeout=300))
            m=j["choices"][0]["message"]
            r=parse(m.get("content") or m.get("reasoning") or "")
            if isinstance(r,dict) and "top_third_has_text" in r: return aid, r
        except Exception as e:
            if attempt==2: return aid, {"error":str(e)[:140]}
    return aid, {"error":"unparseable"}

if __name__=="__main__":
    cands=json.load(open("candidates.json"))
    done=json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo=[c for c in cands if str(c["aweme_id"]) not in done]
    print(f"[cand] screening {len(todo)} candidates ({len(done)} cached)")
    with ThreadPoolExecutor(max_workers=5) as ex:
        for n,f in enumerate(as_completed([ex.submit(screen,c) for c in todo]),1):
            aid,r=f.result(); done[aid]=r
            flag="TEXT" if r.get("top_third_has_text") else ("ERR" if r.get("error") else "CLEAR")
            print(f"  {flag:5} {aid}  {r.get('where') or r.get('error','')}")
            if n%10==0: json.dump(done,open(OUT,"w"),indent=1)
    json.dump(done,open(OUT,"w"),indent=1)
    clear=[k for k,v in done.items() if v.get("top_third_has_text") is False]
    print(f"\n[cand] {len(done)} screened | CLEAR tops: {len(clear)} | need 29")
