#!/usr/bin/env python3
"""Re-render CLE-B6 episodes with the opener the plan assigned (cleora_opener_plan.action='rerender').
Uses the real pipeline (build_new_episode_mac.py) with the episode's own local voiceover (~/cleora-render/tts_epNNN.json).
Local only: writes ~/cleora-render/rerender_staging/<id>.mp4. Needs ~/cleora-render/OpenMontage/.venv (ffmpeg/ffprobe) and SUPABASE_KEY."""
import json, os, sys, glob, shutil, subprocess, time, urllib.request
HOME=os.path.expanduser("~"); CR=f"{HOME}/cleora-render"; ST=f"{CR}/rerender_staging"
REF="qlcmgxgwpzmiebzxflai"; KEY=os.environ["SUPABASE_KEY"]
def rest(path):
    r=urllib.request.Request(f"https://{REF}.supabase.co/rest/v1/{path}",headers={"apikey":KEY,"Authorization":"Bearer "+KEY})
    return json.loads(urllib.request.urlopen(r,timeout=60).read())
ids=sys.argv[1:] or [r["content_id"] for r in rest("cleora_opener_plan?select=content_id,seq&action=eq.rerender&rerendered=eq.false&content_id=like.CLE-B6-*&order=seq")]
os.makedirs(f"{ST}/frames",exist_ok=True)
env=dict(os.environ); env["PATH"]=f"{CR}/OpenMontage/.venv/bin:"+env["PATH"]
for cid in ids:
    n=int(cid.rsplit("-",1)[1]); ep=f"ep{n:03d}"; t0=time.time()
    rc=subprocess.run(["python",f"{CR}/content-render-scripts/cleora/mac/build_new_episode_mac.py",ep,cid,f"{CR}/tts_{ep}.json"],cwd=f"{CR}/cleora-batch",env=env,
                      stdout=open(f"/tmp/{ep}_render.log","w"),stderr=subprocess.STDOUT,timeout=900).returncode
    outs=sorted(glob.glob(f"{CR}/OpenMontage/projects/cleora-{ep}-*/renders/{ep}_*.mp4"),key=os.path.getmtime)
    ok=rc==0 and outs and os.path.getmtime(outs[-1])>t0
    if ok:
        shutil.copy(outs[-1],f"{ST}/{cid}.mp4")
        for d in glob.glob(f"{CR}/OpenMontage/projects/cleora-{ep}-*"):          # free ~350 MB of intermediates
            shutil.rmtree(f"{d}/assets",ignore_errors=True)
    print(cid,"OK" if ok else f"FAILED rc={rc} (see /tmp/{ep}_render.log)",f"{round(time.time()-t0)}s",flush=True)
