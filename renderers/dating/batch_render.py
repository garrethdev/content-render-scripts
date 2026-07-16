import json, os, subprocess, urllib.request, glob, time

def load(p=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for l in open(p):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
K=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip().strip('"')
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":K,"Authorization":"Bearer "+K}

rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=gte.60&select=id,transcript,clip_text",headers=H)))
tr={r["id"]:(r.get("transcript") or r.get("clip_text") or "").replace("\n"," ")[:400] for r in rows}

files=sorted(glob.glob("variants/dr_*_v*.mp4"))
done=fail=0
t0=time.time()
files=[f for f in files if '_104_' not in f and '_115_' not in f]
for f in files:
    base=os.path.basename(f).replace(".mp4","")          # dr_62_v1
    sid=int(base.split("_")[1]); ver=base.split("_")[2]
    out=f"renders/DR-{sid:03d}-{ver}.mp4"
    if os.path.exists(out) and os.path.getsize(out)>0:
        print(f"skip {out} (exists)"); done+=1; continue
    rc=subprocess.run(["./.venv/bin/python3","scripts/run_pipeline.py",
        "--source",f,"--reaction","assets/kitchen2_v2_cut_dating2.mp4","--reaction-trim","0","--reaction-dur","8.4",
        "--cutout","assets/char3_cutout.webm","--out",out,
        "--transcript",tr.get(sid,""),"--hook-dur","1.8"],capture_output=True,text=True)
    if rc.returncode==0 and os.path.exists(out):
        done+=1; print(f"OK {out}  [{done+fail}/{len(files)}  {int(time.time()-t0)}s]")
    else:
        fail+=1
        print(f"FAIL {out}: {rc.stderr.strip().splitlines()[-1] if rc.stderr.strip() else 'unknown'}")
print(f"BATCH DONE: {done} ok, {fail} failed of {len(files)}")
