#!/usr/bin/env python3
"""v3 batch: 10 realism-upgraded slide-1 images via fal-ai/gpt-image-2/edit."""
import fal_client, os, json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

OUT = os.path.expanduser("~/Claude/jessicas-aesthetic/yara-dump/out2")
REF = open(os.path.expanduser("~/Claude/jessicas-aesthetic/char3/ref_url.txt")).read().strip()
os.makedirs(OUT, exist_ok=True)
PROMPTS_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/Claude/jessicas-aesthetic/images/yara-dump/comp_fallback11.json")
prompts = json.load(open(PROMPTS_FILE))

def _call(prompt):
    res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
        arguments={"prompt": prompt, "image_urls": [REF],
                   "num_images": 1, "image_size": "portrait_16_9"})
    return res["images"][0]["url"]

def gen(item):
    idx, prompt, scene = item["id"], item["prompt"], item["scene"]
    for attempt in range(3):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                url = ex.submit(_call, prompt).result(timeout=120)
            fn = os.path.join(OUT, f"comp_{idx:02d}.jpg")
            urllib.request.urlretrieve(url, fn)
            return f"OK  comp_{idx:02d}  ({scene[:40]})"
        except Futed:
            print(f"comp_{idx:02d} attempt {attempt+1} timeout, retry", flush=True)
        except Exception as e:
            msg = str(e)[:110]
            print(f"comp_{idx:02d} attempt {attempt+1} err: {msg}", flush=True)
            if "Exhausted balance" in msg or "locked" in msg:
                return f"BALANCE  comp_{idx:02d}"
    return f"FAIL comp_{idx:02d}"

if __name__ == "__main__":
    print(f"v3 batch: {len(prompts)} images", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, prompts):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
