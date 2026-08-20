#!/usr/bin/env python3
"""Pull on-screen hooks from the n8n Filler Hookmaker, chunked (Code node has a 60s cap
and the LLM node maxTokens=4000, so 50 clips in one call would truncate)."""
import json, time, urllib.request

URL = "https://czed.app.n8n.cloud/webhook/filler-hookmaker"
CHUNK = 10
req = json.load(open("hook_request.json"))
items, per = req["items"], req["count"]

out = {}
for i in range(0, len(items), CHUNK):
    batch = items[i:i+CHUNK]
    body = json.dumps({"count": per, "items": batch}).encode()
    r = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        resp = json.load(urllib.request.urlopen(r, timeout=180))
    except Exception as e:
        print(f"  chunk {i//CHUNK+1} FAILED: {e}"); continue
    got = 0
    for res in resp.get("results", []):
        hooks = res.get("hooks") or []
        if hooks:
            out[str(res["content_id"])] = hooks; got += len(hooks)
    rej = sum(len(res.get("rejected") or []) for res in resp.get("results", []))
    print(f"  chunk {i//CHUNK+1}: {len(batch)} clips -> {got} hooks kept, {rej} rejected ({time.time()-t:.0f}s)")

json.dump(out, open("hooks.json", "w"), indent=1)
short = [k for k, v in out.items() if len(v) < 2]
print(f"\nclips with hooks: {len(out)}/{len(items)} | total hooks: {sum(len(v) for v in out.values())}")
print(f"clips with <2 hooks (need 2 variants): {len(short)}")
