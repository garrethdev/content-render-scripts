import json, os, time, urllib.request, urllib.parse

def load(path=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for line in open(path):
        line=line.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
def unq(s): return (s or "").strip().strip('"').strip("'")
KEY=unq(os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY"))
SCK=unq(os.environ.get("SCRAPECREATORS_API_KEY"))
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":KEY,"Authorization":"Bearer "+KEY,"Content-Type":"application/json"}

IDS=[60,62,64,70,104,110,111,113,115,117,119,120,123,125,128,129,130,131,132,133,134]
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,url,handle,caption,complaint_flavor,transcript,text_hook_content,clip_text"%",".join(map(str,IDS)),headers=H)))

def clean_vtt(t):
    if not t: return ""
    out=[]
    for ln in str(t).split("\n"):
        s=ln.strip()
        if not s or s=="WEBVTT" or "-->" in s or s.isdigit(): continue
        out.append(s)
    return " ".join(out).strip()

# 1) transcripts for rows missing them
for r in rows:
    if r.get("transcript") and len(r["transcript"])>20: continue
    try:
        t=json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.scrapecreators.com/v1/tiktok/video/transcript?url="+urllib.parse.quote(r["url"],safe=""),
            headers={"x-api-key":SCK}),timeout=60))
        tr=clean_vtt(t.get("transcript"))
    except Exception as e:
        print(f"id={r['id']} transcript fetch FAILED: {e}"); tr=""
    if tr:
        urllib.request.urlopen(urllib.request.Request(
            SB+"/rest/v1/dating_reaction_sources?id=eq."+str(r["id"]),
            data=json.dumps({"transcript":tr}).encode(),method="PATCH",
            headers={**H,"Prefer":"return=minimal"}))
        r["transcript"]=tr
        print(f"id={r['id']} transcript: {tr[:60]!r}")
    else:
        print(f"id={r['id']} NO SPEECH FOUND")

# 2) re-fire hookmaker for rows without a real top pick
time.sleep(3)
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,handle,complaint_flavor,clip_text,transcript,caption,text_hook_content"%",".join(map(str,IDS)),headers=H)))
need=[r for r in rows if not (r.get("text_hook_content") and len(r["text_hook_content"])>5)]
print(f"\nre-hooking {len(need)} rows")
ok=fail=0
for r in need:
    req=urllib.request.Request("https://czed.app.n8n.cloud/webhook/dating-genre-hookmaker",
        data=json.dumps(r).encode(),method="POST",headers={"Content-Type":"application/json"})
    try:
        urllib.request.urlopen(req,timeout=180); ok+=1; print(f"id={r['id']} re-hooked")
    except Exception as e:
        fail+=1; print(f"id={r['id']} FAILED: {e}")
    time.sleep(20)
print(f"DONE rehook: {ok} ok, {fail} failed")
