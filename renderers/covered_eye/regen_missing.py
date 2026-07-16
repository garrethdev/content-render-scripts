#!/usr/bin/env python3
"""Regenerate specific missing slide-1 indices with timeout + retry."""
import fal_client, os, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed
from slide1_promptmaker import build_bank, REF, OUT

MISSING = [int(x) for x in sys.argv[1:]] or [7,25,26,27,28,29,30]
bank = {i: p for i, p in build_bank(30, 0)}

def soften(p):
    return (p.replace("slim toned athletic figure, flat stomach", "fit, healthy, athletic figure")
             .replace("slim and toned with a flat stomach, athletic figure", "fit and healthy with an athletic figure"))

def _call(prompt):
    res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
        arguments={"prompt": prompt, "image_urls": [REF],
                   "num_images": 1, "image_size": "portrait_16_9"})
    return res["images"][0]["url"]

def gen(idx):
    prompt = soften(bank[idx])
    for attempt in range(3):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                url = ex.submit(_call, prompt).result(timeout=100)
            fn = os.path.join(OUT, f"slide1_{idx:02d}.jpg")
            urllib.request.urlretrieve(url, fn)
            return f"idx {idx} OK ({os.path.basename(fn)})"
        except Futed:
            print(f"idx {idx} attempt {attempt+1} timed out, retry", flush=True)
        except Exception as e:
            print(f"idx {idx} attempt {attempt+1} err: {str(e)[:90]}", flush=True)
    return f"idx {idx} GAVE UP"

if __name__ == "__main__":
    print("regen:", MISSING, flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, MISSING):
            print(r, flush=True)
    print("REGEN DONE", flush=True)
