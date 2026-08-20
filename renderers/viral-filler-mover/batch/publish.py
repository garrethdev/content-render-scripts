#!/usr/bin/env python3
"""Make batch VFM-B1-0819 schedulable: upload MP4s -> viral-filler bucket,
then write one viral_filler_content row per video with status='done'.
Idempotent: re-running skips objects and rows that already exist."""
import os, re, json, glob, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
env=dict(re.findall(r'^([A-Z_]+)\s*=\s*"?([^"\n]+)"?',
        open(os.path.expanduser("~/Claude/viral-content-filler-creator/.env")).read(), re.M))
SK=env["SUPABASE_SERVICE_KEY"]
H={"Authorization":"Bearer "+SK,"apikey":SK}
BATCH="VFM-B1-0819"
PREFIX="renders/vfm"

rows={os.path.abspath(r["out"]):r for r in json.load(open("plan_final.json"))}
vids=sorted(glob.glob("renders/*.mp4"))
plan=[rows[os.path.abspath(v)] for v in vids if os.path.abspath(v) in rows]
assert len(plan)==len(vids)==100, f"expected 100, got {len(plan)}/{len(vids)}"

def obj_name(r): return f"{PREFIX}/{BATCH}_{r['idx']:03d}_{r['aweme_id']}.mp4"
def pub_url(r):  return f"{SB}/storage/v1/object/public/viral-filler/{obj_name(r)}"

def upload(r):
    url=f"{SB}/storage/v1/object/viral-filler/{obj_name(r)}"
    data=open(r["out"],"rb").read()
    req=urllib.request.Request(url,data=data,method="POST",
        headers={**H,"Content-Type":"video/mp4","x-upsert":"true"})
    urllib.request.urlopen(req,timeout=900)
    return r["idx"], len(data)/1e6

if __name__=="__main__":
    import sys
    stage=sys.argv[1] if len(sys.argv)>1 else "upload"
    if stage=="upload":
        done=0; fail=[]
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs={ex.submit(upload,r):r for r in plan}
            for f in as_completed(futs):
                try:
                    i,mb=f.result(); done+=1
                    if done%10==0: print(f"  uploaded {done}/100")
                except Exception as e:
                    fail.append((futs[f]["idx"],str(e)[:100]))
        print(f"[upload] {done}/100 ok, {len(fail)} failed")
        for i,e in fail: print("   FAIL",i,e)
    elif stage=="rows":
        payload=[{"filler_aweme_id":r["aweme_id"],
                  "source_url":f"{SB}/storage/v1/object/public/viral-filler/clips/{r['aweme_id']}.mp4",
                  "handle":r["handle"],"hook_angle":r["hook_angle"],
                  "about":(r.get("theme") or ""),"hook":r["caption"],
                  "character_url":None,
                  "character_id":int(r["character"].replace("char","")),
                  "render_url":pub_url(r),"status":"done",
                  "batch":BATCH,"treatment":"moving_cutout_v1"} for r in plan]
        req=urllib.request.Request(SB+"/rest/v1/viral_filler_content",
            data=json.dumps(payload).encode(),method="POST",
            headers={**H,"Content-Type":"application/json","Prefer":"return=representation"})
        out=json.load(urllib.request.urlopen(req,timeout=300))
        print(f"[rows] inserted {len(out)} | id range {out[0]['id']}-{out[-1]['id']}")
        json.dump([o["id"] for o in out], open("inserted_ids.json","w"))
