import json, os, sys, time, urllib.request

def load(p=os.path.expanduser("~/.config/peptide-secrets/.env")):
    for l in open(p):
        l=l.strip()
        if l and not l.startswith("#") and "=" in l:
            k,v=l.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load()
K=os.environ["CAROUSEL_SUPABASE_SECRET_KEY"].strip().strip('"')
SB="https://qlcmgxgwpzmiebzxflai.supabase.co"
H={"apikey":K,"Authorization":"Bearer "+K}

ids=sys.argv[1].split(",")
CONFIG={
 "source":{"table":"dating_reaction_sources",
           "filter":"id=in.(%s)&social_caption=is.null"%",".join(ids),
           "id_column":"id",
           "context_columns":["transcript","clip_text","caption","complaint_flavor","handle"]},
 "voice":{"system_prompt":("You write Instagram/TikTok captions for Peptide Miracles dating reaction videos aimed at plus-size Black women. "
   "Voice: a plain-spoken woman saying the quiet part out loud about dating while plus size. Structure: (1) one blunt opening truth tied to THIS clip's situation, "
   "(2) 2-4 sentences riffing on the specific moment from the context (the man, the app, the date, the double standard), real and conversational, no corporate tone, "
   "(3) pivot: Peptide Miracles shows Black women how to get peptides that actually work for our bodies, not the typical skinny girl, "
   "(4) CTA line: Type \"Body\" in the comments for access. "
   "Rules: no em dashes, no ampersands, never name brand drugs (no ozempic, wegovy, zepbound, semaglutide, tirzepatide). Generic terms like peptides or GLP-1 are fine. 60-120 words before hashtags."),
  "banned_words":["ozempic","wegovy","zepbound","semaglutide","tirzepatide"]},
 "output":{"target_column":"social_caption"},
 "format":{"hashtag_stack":"#peptidemiracles #glp1 #plussizedating #datingstruggles #curvygirl #weightlossjourney #bodyconfidence"}
}
req=urllib.request.Request("https://czed.app.n8n.cloud/webhook/caption-maker",
    data=json.dumps(CONFIG).encode(),method="POST",headers={"Content-Type":"application/json"})
try:
    resp=urllib.request.urlopen(req,timeout=300)
    print("webhook status:",resp.status)
except Exception as e:
    print("webhook error:",e)
time.sleep(5)
rows=json.load(urllib.request.urlopen(urllib.request.Request(
    SB+"/rest/v1/dating_reaction_sources?id=in.(%s)&select=id,social_caption"%",".join(ids),headers=H)))
for r in rows:
    c=r.get("social_caption") or ""
    print(f"\n--- id={r['id']} ({len(c)} chars) ---\n{c[:400]}")
