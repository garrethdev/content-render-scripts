import json, os, time, urllib.request

def load(path=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for line in open(path):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
KEY=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip().strip('"').strip("'")
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":KEY,"Authorization":"Bearer "+KEY}

IDS=[60,62,64,70,104,110,111,113,115,117,119,120,123,125,128,129,130,131,132,133,134]
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,handle,complaint_flavor,clip_text,transcript,caption,text_hook_content"%",".join(map(str,IDS)),headers=H)))
print(f"{len(rows)} rows to hook")
ok=fail=0
for r in rows:
    body=json.dumps(r).encode()
    req=urllib.request.Request("https://czed.app.n8n.cloud/webhook/dating-genre-hookmaker",
        data=body,method="POST",headers={"Content-Type":"application/json"})
    try:
        resp=json.load(urllib.request.urlopen(req,timeout=180))
        hooks=resp.get("hook_count","?")
        top=(resp.get("top_pick") or "")[:70]
        print(f"id={r['id']} @{r['handle']}: {hooks} hooks | {top}")
        ok+=1
    except Exception as e:
        print(f"id={r['id']} FAILED: {e}")
        fail+=1
    time.sleep(20)
print(f"DONE hooks: {ok} ok, {fail} failed")
