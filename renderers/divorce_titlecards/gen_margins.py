#!/usr/bin/env python3
"""4 margin variations of v4 vintage two-line, 9:16 for TikTok."""
import fal_client, os, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

OUT = os.path.expanduser("~/Claude/divorce-horror-stories/out")

BASE = ('Retro 1970s horror-comic title graphic on a solid black background. '
        'The text "DIVORCE HORROR STORIES" in {color} dripping letters with subtle '
        'grainy halftone print texture inside the letterforms, drips running down like old '
        'poster ink. Text wraps across two stacked centered lines: "DIVORCE HORROR" on the '
        'first line, "STORIES" on the second line, both centered. {style} '
        'The text block occupies only the central 70% of the frame width, with generous '
        'empty black margins on the left and right sides and comfortable black space above '
        'and below. No letter or drip touches the frame edges. Distressed vintage print '
        'feel, no other elements.')

PROMPTS = {
    "m1_straight": BASE.format(color="faded hot pink",
        style="Straight horizontal baselines, no arch or tilt."),
    "m2_arched": BASE.format(color="faded hot pink",
        style="The lines of text arch and wave playfully like a 1970s horror poster."),
    "m3_bold": BASE.format(color="faded hot pink",
        style="Extra thick condensed letterforms with slightly heavier drips. "
              "Straight horizontal baselines."),
    "m4_bright": BASE.format(color="vivid hot pink",
        style="Straight horizontal baselines, no arch or tilt."),
}

def _call(prompt):
    res = fal_client.subscribe("fal-ai/gpt-image-2",
        arguments={"prompt": prompt, "num_images": 1,
                   "image_size": {"width": 1088, "height": 1920},
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
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, PROMPTS.items()):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
