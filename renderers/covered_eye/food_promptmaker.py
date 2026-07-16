#!/usr/bin/env python3
"""
Food flat-lay generator — slides 2-6 (jessicas_tt aesthetic -> Peptide Miracles).
Overhead white-bowl-on-marble meal shots, iPhone realism, NO text baked in
(copy is overlaid at render time). Model: fal-ai/gpt-image-2 text-to-image
(no likeness reference needed for food).
Usage: python3 food_promptmaker.py <count> [start_idx]
"""
import fal_client, os, json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Futed

OUT = os.path.expanduser("~/Claude/jessicas-aesthetic/images/food")
os.makedirs(OUT, exist_ok=True)

STYLE = ("Directly overhead 90-degree flat-lay photo taken on an iPhone, one white ceramic bowl "
         "centered on a light grey-and-white marble kitchen counter. Casual everyday phone photo, "
         "soft natural daylight from a window, gentle soft shadow under the bowl, subtle sensor "
         "grain, slight HDR flatness, imperfect white balance, framing a touch off-center and "
         "slightly tilted. The food looks fresh, colorful and abundant, styled loosely by hand, "
         "not perfectly arranged. Vertical 9:16, plenty of clean marble space above and below the "
         "bowl for text overlay. No hands, no people, no text, no labels. Not glossy, not "
         "editorial, not commercial food photography, not perfect.")

MEALS = [
    # breakfast (slide 2)
    ("breakfast", "a breakfast bowl with sliced avocado, two soft boiled eggs cut open, sliced kiwi, a handful of blueberries, small cubes of cheese and a piece of seared beef"),
    ("breakfast", "a breakfast bowl with greek yogurt, chia seeds, sliced strawberries, banana coins, a drizzle of honey and a few walnuts"),
    ("breakfast", "a breakfast bowl with scrambled eggs, sliced avocado, cherry tomatoes, a slice of smoked salmon and fresh dill"),
    # lunch (slide 3)
    ("lunch", "a lunch bowl with sliced grilled chicken breast, white rice, cherry tomatoes, cucumber slices and a lemon wedge"),
    ("lunch", "a chopped salad bowl with cucumber, cherry tomatoes, red onion, feta cheese crumbles and herbs"),
    ("lunch", "a lunch bowl with seared salmon, quinoa, shaved carrots, edamame and sliced radish"),
    # snack (slide 4)
    ("snack", "a small bowl with orange segments and crisp green apple slices"),
    ("snack", "a small scalloped bowl with three medjool dates stuffed with nut butter and a square of dark chocolate"),
    ("snack", "a small bowl with greek yogurt, pomegranate seeds, kiwi slices and a square of dark chocolate"),
    # dinner (slide 5)
    ("dinner", "a dinner bowl with sliced grilled steak, green beans and roasted golden potatoes with a small dollop of herb butter"),
    ("dinner", "a dinner bowl with blackened chicken slices over caesar salad with shaved parmesan"),
    ("dinner", "a dinner bowl with baked white fish, roasted broccolini and sweet potato wedges"),
    # dessert (slide 6)
    ("dessert", "a fruit bowl with strawberry halves, mango cubes, banana slices, blueberries and kiwi arranged loosely"),
    ("dessert", "a small bowl of thick greek yogurt swirled with crushed raspberries, dark chocolate shavings and a few pistachios"),
    ("dessert", "a small bowl with baked cinnamon apple slices, a scoop of greek yogurt and chopped pecans"),
]

def make_prompt(desc):
    return f"{STYLE} The bowl contains {desc}."

def _call(prompt):
    res = fal_client.subscribe("fal-ai/gpt-image-2",
        arguments={"prompt": prompt, "num_images": 1, "image_size": "portrait_16_9"})
    return res["images"][0]["url"]

def gen(item):
    idx, (meal, desc) = item
    prompt = make_prompt(desc)
    for attempt in range(3):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                url = ex.submit(_call, prompt).result(timeout=120)
            fn = os.path.join(OUT, f"food_{idx:02d}_{meal}.jpg")
            urllib.request.urlretrieve(url, fn)
            return f"OK  food_{idx:02d}_{meal}"
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
    picks = [(start + i + 1, MEALS[(start + i) % len(MEALS)]) for i in range(n)]
    json.dump({i: make_prompt(m[1]) for i, m in picks},
              open(os.path.join(OUT, "prompts_used.json"), "w"), indent=1)
    print(f"food batch: {len(picks)} images", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(gen, picks):
            print(r, flush=True)
    print("BATCH DONE", flush=True)
