#!/usr/bin/env python3
"""Queue the newer (re-rendered) Cleora videos on SuperWarm, in cleora_opener_plan order, up to the queue cap.
Env: SW (SuperWarm API key), SUPABASE_KEY (anon, read). --dry shows the plan only.
Only queues episodes whose re-render exists in ~/cleora-render/rerender_staging and that are not already queued/posted."""
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
SW=os.environ["SW"]; KEY=os.environ["SUPABASE_KEY"]; JOB="39acfe3d-5ea3-4670-8c56-22e4f0b8ee50"; CAP=36
API="https://superwarm.co/api/public"; REF="qlcmgxgwpzmiebzxflai"; ST=os.path.expanduser("~/cleora-render/rerender_staging")
HT="\n\n#wellness #chinesemedicineworks #healing #ancientwisdom #holistichealth"; DRY="--dry" in sys.argv
def sw(m,p,b=None):
    r=urllib.request.Request(API+p,method=m,data=json.dumps(b).encode() if b is not None else None,headers={"Authorization":"Bearer "+SW,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r,timeout=120) as x: return x.status,json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read())
        except Exception: return e.code,{}
def db(path):
    r=urllib.request.Request(f"https://{REF}.supabase.co/rest/v1/{path}",headers={"apikey":KEY,"Authorization":"Bearer "+KEY})
    return json.loads(urllib.request.urlopen(r,timeout=60).read())
s,d=sw("GET",f"/accounts/{JOB}/queue"); assert s==200,(s,d)
pending=[i for i in d["items"] if i["status"]=="pending"]; room=CAP-len(pending)
print(f"pending {len(pending)} / cap {CAP} -> room for {room}")
plan=db("cleora_opener_plan?select=content_id,seq,new_first_frame,look_alike_family&order=seq")
cont={r["content_id"]:r for r in db("cleora_content?select=content_id,caption,posting_status&content_id=like.CLE-B6-*")}
todo=[p for p in plan if os.path.exists(f"{ST}/{p['content_id']}.mp4") and cont[p["content_id"]]["posting_status"] not in ("superwarm_queued","Posted")]
todo=todo[:max(room,0)]
for p in todo: print(f"  would queue seq {p['seq']:>2} {p['content_id']} {p['new_first_frame']}")
if DRY or not todo: sys.exit(0)
out={}
for p in todo:
    c=p["content_id"]; cap=cont[c]["caption"] or ""; cap=cap+(HT if "#" not in cap else "")
    s,u=sw("GET","/upload-url?"+urllib.parse.urlencode({"filename":f"{c}.mp4","contentType":"video/mp4"})); assert s==200,(s,u)
    rq=urllib.request.Request(u["signedUrl"],method="PUT",data=open(f"{ST}/{c}.mp4","rb").read(),headers={"Content-Type":"video/mp4"})
    with urllib.request.urlopen(rq,timeout=900) as x: assert x.status in (200,201)
    s,a=sw("POST","/content",{"jobId":JOB,"postType":"video","videoUrl":u["publicUrl"],"caption":cap,"music":"original"}); assert s in (200,201),(c,s,a)
    out[c]={"item_id":a["item"]["id"],"public_url":u["publicUrl"]}; print("  queued",c,"pos",a.get("queuePosition"),flush=True); time.sleep(1.5)
json.dump(out,open("superwarm_queue_result.json","w"),indent=1)
print("done. Now sync the database (posting_status/superwarm_item_id/video_public_url) - see the handover note, section 'DB bookkeeping'.")
