#!/usr/bin/env python3
"""
Food flat-lay generator — uses her CLEAN food photos as STYLE references.
Feeds a food_ref_clean image into fal-ai/gpt-image-2/edit as a style/lighting/framing
anchor, then plates a DIFFERENT original meal in that exact aesthetic. Output is new
(publish-safe), not a copy of her dish. NO text baked in (copy overlaid at render time).

Usage: python3 food_ref_generator.py <count> [start_idx]
"""
import fal_client, os, json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

BASE = os.path.expanduser("~/Claude/jessicas-aesthetic")
CLEAN = os.path.join(BASE, "content/food_ref_clean")
OUT = os.path.join(BASE, "images/food")
CACHE = os.path.join(BASE, "content/food_ref_urls.json")
os.makedirs(OUT, exist_ok=True)

# style anchors = the FOOD refs in the clean folder (r-prefixed), not the v3 character shots
FOOD_REFS = sorted(f for f in os.listdir(CLEAN) if f.startswith("r") and f.endswith(".jpg"))

# original target meals (deliberately DIFFERENT from her dishes) x carousel slot
MEALS = [
    ("breakfast", "a breakfast bowl of greek yogurt, sliced banana, raspberries, a spoon of almond butter and a sprinkle of granola"),
    ("breakfast", "a breakfast bowl of scrambled eggs, smashed avocado, cherry tomatoes and a few slices of smoked salmon"),
    ("breakfast", "a breakfast bowl of oats topped with sliced strawberries, blueberries, chia seeds and a drizzle of honey"),
    ("lunch", "a lunch bowl of grilled chicken, white rice, steamed broccolini and shredded carrot"),
    ("lunch", "a chopped salad bowl of cucumber, cherry tomato, red onion, chickpeas and feta"),
    ("lunch", "a lunch bowl of seared salmon, quinoa, edamame and sliced radish"),
    ("snack", "a small bowl of orange segments and green apple slices"),
    ("snack", "a small bowl of cottage cheese with peach slices and crushed pistachios"),
    ("snack", "a small bowl of greek yogurt with pomegranate seeds and a square of dark chocolate"),
    ("dinner", "a dinner bowl of sliced steak, roasted green beans and golden baby potatoes"),
    ("dinner", "a dinner bowl of grilled shrimp over arugula with mango and avocado"),
    ("dinner", "a dinner bowl of baked white fish, roasted sweet potato and sauteed spinach"),
    ("dessert", "a fruit bowl of strawberry halves, mango cubes, kiwi and blueberries"),
    ("dessert", "a small bowl of greek yogurt swirled with crushed raspberry and dark chocolate shavings"),
    ("dessert", "a small bowl of baked cinnamon apple with yogurt and chopped pecans"),
]

def load_cache():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}

def ref_url(fname, cache):
    if fname not in cache:
        cache[fname] = fal_client.upload_file(os.path.join(CLEAN, fname))
        json.dump(cache, open(CACHE, "w"), indent=1)
    return cache[fname]

PROMPT = (
    "Use the attached photo ONLY as a style, lighting, camera-angle and surface reference. "
    "Match its look exactly: a directly-overhead 90-degree flat-lay, a single white ceramic "
    "bowl centered on cool light-grey and white marble, soft even natural daylight, a gentle "
    "soft shadow, subtle iPhone photo grain, slightly imperfect white balance, and generous "
    "empty marble space above and below the bowl. Do NOT copy the same food. Instead plate a "
    "completely different, original meal: {meal}. Fresh, colorful, loosely styled by hand, not "
    "perfectly arranged. Vertical 9:16. No text, no labels, no people, no hands. Not glossy, "
    "not commercial food photography, not perfect.")

def _call(prompt, url):
    res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
        arguments={"prompt": prompt, "image_urls": [url],
                   "num_images": 1, "image_size": "portrait_16_9"})
    return res["images"][0]["url"]

def gen(item):
    idx, (meal, desc), ref, refurl = item
    prompt = PROMPT.format(meal=desc)
    for attempt in range(3):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                out = ex.submit(_call, prompt, refurl).result(timeout=120)
            fn = os.path.join(OUT, f"food_{idx:02d}_{meal}.jpg")
            urllib.request.urlretrieve(out, fn)
            return f"OK  food_{idx:02d}_{meal}  (ref {ref})"
        except Futed:
            print(f"food_{idx:02d} attempt {attempt+1} timeout, retry", flush=True)
        except Exception as e:
            msg = str(e)[:110]
            print(f"food_{idx:02d} attempt {attempt+1} err: {msg}", flush=True)
            if "Exhausted balance" in msg or "locked" in msg:
                return f"BALANCE food_{idx:02d}"
    return f"FAIL food_{idx:02d}"

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cache = load_cache()
    items = []
    for i in range(n):
        meal = MEALS[(start + i) % len(MEALS)]
        ref = FOOD_REFS[(start + i) % len(FOOD_REFS)]  # rotate refs by matching slot
        items.append((start + i + 1, meal, ref, ref_url(ref, cache)))
    print(f"food-ref batch: {len(items)} images (refs from food_ref_clean)", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, items):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
