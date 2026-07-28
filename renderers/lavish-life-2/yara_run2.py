#!/usr/bin/env python3
"""Composition-reference batch: char3 face ref + source-frame composition ref."""
import fal_client, os, json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

OUT = os.path.expanduser("~/Claude/jessicas-aesthetic/yara-dump/out2")
REF = open(os.path.expanduser("~/Claude/jessicas-aesthetic/char3/ref_url.txt")).read().strip()
os.makedirs(OUT, exist_ok=True)
items = json.load(open(sys.argv[1]))
_upload_cache = {}
def upload(path):
    if path not in _upload_cache:
        _upload_cache[path] = fal_client.upload_file(path)
    return _upload_cache[path]

def _call(prompt, src_url):
    res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
        arguments={"prompt": prompt, "image_urls": [REF, src_url],
                   "num_images": 1, "image_size": "portrait_16_9"})
    return res["images"][0]["url"]

def gen(item):
    idx, prompt, scene, src = item["id"], item["prompt"], item["scene"], item["src"]
    try:
        src_url = upload(os.path.expanduser(src))
    except Exception as e:
        return f"UPLOADFAIL c{idx:02d} {str(e)[:60]}"
    for attempt in range(5):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                url = ex.submit(_call, prompt, src_url).result(timeout=150)
            urllib.request.urlretrieve(url, os.path.join(OUT, f"comp_{idx:02d}.jpg"))
            return f"OK  comp_{idx:02d}  ({scene[:40]})"
        except Futed:
            print(f"comp_{idx:02d} attempt {attempt+1} timeout", flush=True)
        except Exception as e:
            print(f"comp_{idx:02d} attempt {attempt+1} err: {str(e)[:100]}", flush=True)
    return f"FAIL comp_{idx:02d}"

if __name__ == "__main__":
    print(f"comp batch: {len(items)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, items):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
