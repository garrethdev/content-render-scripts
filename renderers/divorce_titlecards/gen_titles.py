#!/usr/bin/env python3
"""5 dripping-title variations via fal-ai/gpt-image-2 (text-to-image, no reference)."""
import fal_client, os, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

OUT = os.path.expanduser("~/Claude/divorce-horror-stories/out")
os.makedirs(OUT, exist_ok=True)

PROMPTS = {
    "v1_classic": 'Bold horror-movie title graphic on a pure solid black background. The text "DIVORCE HORROR STORIES" in huge hot pink dripping letters — a thick, rounded horror typeface with glossy melting drips running down from every letter, like dripping paint. Text wraps across three stacked centered lines: "DIVORCE", "HORROR", "STORIES", each filling most of the frame width. Flat vector-style graphic, clean edges, no other elements, no watermark.',
    "v2_neon": 'Horror title graphic on a pure black background. The text "DIVORCE HORROR STORIES" in hot pink dripping letters with a soft neon pink glow radiating off each letter, drips melting downward like wet neon paint. Three stacked centered lines: "DIVORCE", "HORROR", "STORIES". Dark, moody, cinematic title card. No other elements.',
    "v3_slime": 'Playful-creepy title graphic on a solid black background. The text "DIVORCE HORROR STORIES" in bubblegum-pink letters made of thick glossy slime, heavy gloopy drips oozing off every letter with rounded droplets about to fall. Three stacked centered lines: "DIVORCE", "HORROR", "STORIES". Bold, high-contrast, flat black backdrop, no other elements.',
    "v4_vintage": 'Retro 1970s horror-comic title graphic on a solid black background. The text "DIVORCE HORROR STORIES" in faded hot pink dripping letters with subtle grainy halftone print texture inside the letterforms, drips running down like old poster ink. Three stacked centered lines: "DIVORCE", "HORROR", "STORIES". Distressed vintage print feel, no other elements.',
    "v5_melt": 'Dramatic title graphic on a pure black background. The text "DIVORCE HORROR STORIES" in matte hot pink letters melting heavily, with long thin paint streaks dripping far down below each line of text. Three stacked centered lines: "DIVORCE", "HORROR", "STORIES", with drips overlapping the line below. Moody and cinematic, no other elements.',
}

def _call(prompt):
    res = fal_client.subscribe("fal-ai/gpt-image-2",
        arguments={"prompt": prompt, "num_images": 1,
                   "image_size": {"width": 1024, "height": 1536},
                   "quality": "high"})
    return res["images"][0]["url"]

def gen(item):
    name, prompt = item
    for attempt in range(3):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                url = ex.submit(_call, prompt).result(timeout=180)
            fn = os.path.join(OUT, f"{name}.png")
            urllib.request.urlretrieve(url, fn)
            return f"OK  {name}"
        except Futed:
            print(f"{name} attempt {attempt+1} timeout, retry", flush=True)
        except Exception as e:
            msg = str(e)[:110]
            print(f"{name} attempt {attempt+1} err: {msg}", flush=True)
            if "Exhausted balance" in msg or "locked" in msg:
                return f"BALANCE  {name}"
    return f"FAIL {name}"

if __name__ == "__main__":
    print(f"batch: {len(PROMPTS)} images", flush=True)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for r in ex.map(gen, PROMPTS.items()):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
