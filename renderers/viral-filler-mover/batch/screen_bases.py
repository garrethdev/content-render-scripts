#!/usr/bin/env python3
"""Gemini vision screen at the BASE level — the defect is a property of the source clip,
so this costs 1 call per base instead of 1 per rendered video.

For each base, samples frames across the hook window (0-2.6s, when our hook is on screen)
and asks: does the clip carry its OWN burned-in text in the top of frame? Tesseract misses
script/handwritten/low-contrast fonts, which is why the renderer walked our hook onto them.

  python3 screen_bases.py [clips_dir] [out.json]
"""
import os, re, sys, json, glob, base64, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

FF="/opt/homebrew/bin/ffmpeg"; MODEL="google/gemini-2.5-pro"
CLIPS=sys.argv[1] if len(sys.argv)>1 else "clips"
OUT=sys.argv[2] if len(sys.argv)>2 else "base_screen.json"
FR="screen_frames"; os.makedirs(FR,exist_ok=True)

PROMPT="""These are frames from the FIRST 3 SECONDS of a vertical (1080x1920) social video.

We burn our own text hook across the TOP THIRD of the frame during exactly this window.
Your job is to tell us whether that top third is already occupied by the clip's OWN
burned-in text, so we don't stack two blocks of text on top of each other.

Count ALL text baked into the video: captions, titles, stickers, handwritten or script
fonts, low-contrast text, comment-reply screenshots, banners, on-screen labels.
Do NOT count: text on physical objects in the scene (product packaging, signage, clothing
prints, a phone screen being held up), or a platform watermark/username.

Reply ONLY with JSON:
{"top_third_has_text": bool,
 "lowest_clear_y": <0.0-1.0, the highest y where a text block could start and clear ALL of
                   the clip's own text; 0.0 if the whole top third is free>,
 "text_style": "none"|"plain"|"script_or_stylized"|"mixed",
 "where": "<8 words on what text is up there, or 'none'>"}"""

def frames(mp4):
    stem=os.path.splitext(os.path.basename(mp4))[0]; out=[]
    for t in (0.3, 1.2, 2.4):
        p=os.path.join(FR,f"{stem}_{t}.jpg")
        if not os.path.exists(p):
            subprocess.run([FF,"-y","-loglevel","error","-ss",str(t),"-i",mp4,"-frames:v","1",
                            "-vf","scale=600:-2","-q:v","3",p],check=True)
        out.append(p)
    return out

def parse(txt):
    txt=txt.replace("```json","").replace("```","")
    best=None
    for m in re.finditer(r"\{",txt):
        depth=0
        for i in range(m.start(),len(txt)):
            if txt[i]=="{": depth+=1
            elif txt[i]=="}":
                depth-=1
                if depth==0:
                    try: best=json.loads(txt[m.start():i+1])
                    except Exception: pass
                    break
    return best

def screen(mp4):
    content=[{"type":"text","text":PROMPT}]
    for i,p in enumerate(frames(mp4),1):
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
            if isinstance(r,dict) and "top_third_has_text" in r: return r
        except Exception as e:
            if attempt==2: return {"error":str(e)[:140]}
    return {"error":"unparseable after 2 tries"}

if __name__=="__main__":
    vids=sorted(glob.glob(os.path.join(CLIPS,"*.mp4")))
    done=json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo=[v for v in vids if os.path.splitext(os.path.basename(v))[0] not in done]
    print(f"[screen] {len(todo)} bases to screen ({len(done)} cached) -> {MODEL}")
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs={ex.submit(screen,v):v for v in todo}
        for n,f in enumerate(as_completed(futs),1):
            aid=os.path.splitext(os.path.basename(futs[f]))[0]
            done[aid]=f.result()
            r=done[aid]
            flag="TEXT" if r.get("top_third_has_text") else ("ERR" if r.get("error") else "clear")
            print(f"  {flag:5} {aid}  clear_y={r.get('lowest_clear_y')}  {r.get('where') or r.get('error','')}")
            if n%10==0: json.dump(done,open(OUT,"w"),indent=1)
    json.dump(done,open(OUT,"w"),indent=1)
    bad=[k for k,v in done.items() if v.get("top_third_has_text")]
    err=[k for k,v in done.items() if v.get("error")]
    print(f"\n[screen] {len(done)} bases | own-text-in-top-third: {len(bad)} | clear: {len(done)-len(bad)-len(err)} | errors: {len(err)}")
