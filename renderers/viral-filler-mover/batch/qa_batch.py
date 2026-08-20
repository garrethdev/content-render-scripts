#!/usr/bin/env python3
"""Gemini visual QA for the moving-cutout batch (standing rule: QA every visual deliverable).
Samples 2 frames per render (hook window + mid-clip) and asks Gemini for a per-video verdict.
Flags are NOT trusted blind — the caller re-checks flagged frames against pixels.

  python3 qa_batch.py [N]     # N = sample size, default = all renders
"""
import os, re, sys, json, glob, random, subprocess, base64, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, "qa_frames"); os.makedirs(FRAMES, exist_ok=True)
FFMPEG = "/opt/homebrew/bin/ffmpeg"
MODEL = "google/gemini-2.5-pro"

PROMPT = """You are QA-ing a short-form vertical (1080x1920) filler video.

Construction: a real creator's clip fills the whole frame. On top of it we composite
a SECOND person — a photorealistic AI-generated woman, filmed separately against a plain
background, then background-removed so only her body remains. She is usually small (about
a quarter of the frame height), sits near an edge or corner, drifts slowly, and is often
wearing dark or black clothing. She will look like she belongs to a different scene than
the main clip — that is intentional and correct, NOT a defect. A short text hook is burned
over the frame for the first ~2.6 seconds only; it may sit at the top OR lower down if the
top was already occupied by the clip's own text.

Frame 1 is from the hook window. Frame 2 is from mid-clip (hook should be GONE by then).

Answer ONLY with JSON:
{"hook_legible":bool,"hook_fully_onscreen":bool,"hook_covers_face":bool,
 "hook_collides_with_existing_text":bool,"cutout_present":bool,"cutout_clipped_at_edge":bool,
 "cutout_has_black_box_or_halo":bool,"cutout_covers_main_subject_face":bool,
 "hook_still_visible_in_frame2":bool,"verdict":"pass"|"fail","reason":"<12 words"}

Fail ONLY for these, and judge each strictly on what you can SEE:
 - the hook is unreadable, or cut off by the frame edge
 - the hook sits ON TOP OF a face, or ON TOP OF the clip's own burned-in text (overlapping
   them so either is hard to read). Text merely ABOVE or BELOW other text, not touching, PASSES.
 - the composited second woman is genuinely absent from the frame
 - the composited woman has a visible RECTANGULAR BLOCK of background around her — an actual
   box of a different colour framing her body. Her own dark clothing is NOT a box. A soft or
   slightly rough alpha edge is NOT a box. Only fail this if you can trace four straight edges.
 - the composited woman covers the main subject's FACE

Everything else passes. She may overlap bodies, furniture, or the clip's text: that is FINE.
She may look out of place stylistically: that is FINE and expected."""

def frames_for(mp4):
    stem = os.path.splitext(os.path.basename(mp4))[0]
    dur = float(subprocess.run(["/opt/homebrew/bin/ffprobe","-v","error","-show_entries",
        "format=duration","-of","csv=p=0",mp4],capture_output=True,text=True).stdout.strip())
    out = []
    for tag, t in (("hook", 1.2), ("mid", round(dur/2, 1))):
        p = os.path.join(FRAMES, f"{stem}_{tag}.jpg")
        if not os.path.exists(p):
            subprocess.run([FFMPEG,"-y","-loglevel","error","-ss",str(t),"-i",mp4,
                            "-frames:v","1","-vf","scale=540:-2","-q:v","4",p], check=True)
        out.append(p)
    return out

def ask(mp4):
    imgs = frames_for(mp4)
    content = [{"type":"text","text":PROMPT}]
    for i,p in enumerate(imgs,1):
        b = base64.b64encode(open(p,"rb").read()).decode()
        content += [{"type":"text","text":f"Frame {i}:"},
                    {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}}]
    body = {"model":MODEL,"messages":[{"role":"user","content":content}],"max_tokens":3000}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization":"Bearer "+os.environ["OPENROUTER_API_KEY"],
                 "Content-Type":"application/json"})
    j = json.load(urllib.request.urlopen(req, timeout=300))
    txt = j["choices"][0]["message"].get("content") or j["choices"][0]["message"].get("reasoning") or ""
    txt = txt.replace("```json", "").replace("```", "")
    # Gemini emits a reasoning preamble; take the LAST balanced JSON object in the reply
    best = None
    for m in re.finditer(r"\{", txt):
        depth = 0
        for i in range(m.start(), len(txt)):
            if txt[i] == "{": depth += 1
            elif txt[i] == "}":
                depth -= 1
                if depth == 0:
                    try: best = json.loads(txt[m.start():i+1])
                    except Exception: pass
                    break
    if not isinstance(best, dict) or "verdict" not in best:
        return {"verdict":"error","reason":("TRUNCATED " + txt[-110:]) if txt else "empty reply"}
    return best

if __name__ == "__main__":
    vids = sorted(glob.glob(os.path.join(HERE,"renders","*.mp4")))
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(vids)
    if n < len(vids):
        random.Random(19).shuffle(vids); vids = sorted(vids[:n])
    print(f"[qa] {len(vids)} videos -> {MODEL}")
    res = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(ask, v): v for v in vids}
        for f in as_completed(futs):
            v = futs[f]; name = os.path.basename(v)
            try: res[name] = f.result()
            except Exception as e: res[name] = {"verdict":"error","reason":str(e)[:120]}
            r = res[name]
            print(f"  {r.get('verdict','?'):5} {name}  {r.get('reason','')}")
    json.dump(res, open(os.path.join(HERE,"qa_results.json"),"w"), indent=1)
    bad = [k for k,v in res.items() if v.get("verdict") != "pass"]
    print(f"\n[qa] pass {len(res)-len(bad)}/{len(res)} | flagged {len(bad)}")
    for k in bad: print("   FLAG", k, res[k].get("reason",""))
