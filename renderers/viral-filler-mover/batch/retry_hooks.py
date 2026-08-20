#!/usr/bin/env python3
import json, time, urllib.request
URL="https://czed.app.n8n.cloud/webhook/filler-hookmaker"
req=json.load(open("hook_request.json")); have=json.load(open("hooks.json"))
missing=[it for it in req["items"] if str(it["content_id"]) not in have or len(have[str(it["content_id"])])<2]
print("retrying",len(missing),"clips in chunks of 5")
for i in range(0,len(missing),5):
    b=missing[i:i+5]
    body=json.dumps({"count":4,"items":b}).encode()
    r=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
    for attempt in (1,2):
        try: resp=json.load(urllib.request.urlopen(r,timeout=180))
        except Exception as e: print("  fail",e); time.sleep(3); continue
        got=0
        for res in resp.get("results",[]):
            h=res.get("hooks") or []
            if h: have[str(res["content_id"])]=h; got+=len(h)
        print(f"  chunk {i//5+1} attempt {attempt}: {got} hooks")
        if got: break
        time.sleep(3)
json.dump(have,open("hooks.json","w"),indent=1)
still=[str(it["content_id"]) for it in req["items"] if str(it["content_id"]) not in have or len(have[str(it["content_id"])])<2]
print(f"\nclips with >=2 hooks: {len(req['items'])-len(still)}/50 | still short: {len(still)}")
