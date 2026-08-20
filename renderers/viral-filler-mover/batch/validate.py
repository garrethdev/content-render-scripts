#!/usr/bin/env python3
"""Pre-schedule technical validation: every file must be a playable, platform-safe MP4."""
import os, json, glob, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
FP="/opt/homebrew/bin/ffprobe"
def check(v):
    j=json.loads(subprocess.run([FP,"-v","error","-show_streams","-show_format","-of","json",v],
        capture_output=True,text=True).stdout or "{}")
    vs=next((s for s in j.get("streams",[]) if s["codec_type"]=="video"),None)
    a =next((s for s in j.get("streams",[]) if s["codec_type"]=="audio"),None)
    # decode the last second to catch truncated/corrupt tails
    dur=float(j.get("format",{}).get("duration",0))
    tail=subprocess.run(["/opt/homebrew/bin/ffmpeg","-v","error","-ss",str(max(0,dur-1.0)),
        "-i",v,"-f","null","-"],capture_output=True,text=True)
    return {"file":os.path.basename(v),
        "w":vs and vs["width"], "h":vs and vs["height"],
        "vcodec":vs and vs["codec_name"], "pix":vs and vs.get("pix_fmt"),
        "fps":vs and round(eval(vs["r_frame_rate"]),2),
        "acodec":a and a["codec_name"], "ach":a and a.get("channels"), "arate":a and a.get("sample_rate"),
        "dur":round(dur,1), "mb":round(os.path.getsize(v)/1e6,1),
        "faststart":subprocess.run(["/bin/sh","-c",f"head -c 2000 '{v}' | grep -qa moov && echo y || echo n"],
            capture_output=True,text=True).stdout.strip(),
        "tail_err":(tail.stderr.strip()[:80] or "")}
vids=sorted(glob.glob("renders/*.mp4"))
res=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    for f in as_completed([ex.submit(check,v) for v in vids]): res.append(f.result())
json.dump(res,open("validate.json","w"),indent=1)
bad=[]
for r in res:
    p=[]
    if (r["w"],r["h"])!=(1080,1920): p.append(f"res {r['w']}x{r['h']}")
    if r["vcodec"]!="h264": p.append("vcodec "+str(r["vcodec"]))
    if r["pix"]!="yuv420p": p.append("pix "+str(r["pix"]))
    if not r["acodec"]: p.append("NO AUDIO")
    if r["faststart"]!="y": p.append("no faststart")
    if r["tail_err"]: p.append("tail: "+r["tail_err"])
    if not (5 <= r["dur"] <= 600): p.append(f"dur {r['dur']}")
    if p: bad.append((r["file"],p))
print(f"validated {len(res)} files")
import collections
print("  resolution:", dict(collections.Counter(f"{r['w']}x{r['h']}" for r in res)))
print("  video:", dict(collections.Counter(f"{r['vcodec']}/{r['pix']}/{r['fps']}fps" for r in res)))
print("  audio:", dict(collections.Counter(f"{r['acodec']}/{r['ach']}ch/{r['arate']}Hz" for r in res)))
print("  faststart:", dict(collections.Counter(r["faststart"] for r in res)))
print(f"  duration {min(r['dur'] for r in res)}-{max(r['dur'] for r in res)}s | total {sum(r['mb'] for r in res)/1000:.1f} GB")
print(f"\nPROBLEMS: {len(bad)}")
for f,p in bad: print("  ",f,p)
