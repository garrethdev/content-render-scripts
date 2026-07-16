#!/usr/bin/env python3
"""
Slide-1 Prompt Maker + Batch Generator  (jessicas_tt aesthetic -> Peptide Miracles)
Replicates the @jessicas_tt HOOK slide: full-body mirror selfie, phone covering one eye,
black activewear, warm luxury yoga/pilates studio or high-end gym.
Character 3 likeness anchored via nano-banana (Gemini 2.5 Flash Image) edit.
"""
import fal_client, os, urllib.request, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

OUT = os.path.expanduser("~/Claude/jessicas-aesthetic/images")
REF = open(os.path.expanduser("~/Claude/jessicas-aesthetic/char3/ref_url.txt")).read().strip()
os.makedirs(OUT, exist_ok=True)

# --- aesthetic DNA (locked from analysis of @jessicas_tt + user-approved winners #3/#8) ---
# HARD RULES that made the winners work: standing full-body, phone FULLY over one eye,
# real room with depth (not cut-out / composited), casual iPhone snapshot.
EYE = ("She holds her phone up at eye level so the phone COMPLETELY covers one of her eyes — "
       "only her other eye, cheek and mouth are visible above the phone. The phone must hide one eye.")
STYLE = ("Casual natural iPhone mirror selfie, subtle grain, cozy luxury wellness aesthetic, muted "
         "warm tones, soft ambient lighting. She is standing, full body head to toe, real reflection "
         "in a large full-length mirror, in a real room with natural depth and perspective — NOT a "
         "cut-out, NOT composited, NOT a flat studio backdrop. Her free arm rests naturally at her "
         "side. Vertical 9:16. Keep her face, dark skin tone and long dark hair identical to the "
         "reference. She is slim and toned with a flat stomach, athletic figure.")

OUTFITS = [
    "a fitted black sports bra and black high-waisted full-length leggings",
    "a black sports bra and black cycling bike shorts",
    "a sleek black one-piece activewear unitard",
    "a black racerback sports bra and black leggings",
]

SETTINGS = [
    # yoga / pilates
    "a high-end pilates studio with warm honey-toned wood floors, a reformer machine, floor-to-ceiling mirrors, soft diffused daylight and a small vase of white tulips",
    "a minimalist yoga studio with a warm wood-panelled wall, a rolled yoga mat on the floor, soft ambient uplighting along the baseboard, cozy warm tones",
    "a bright airy pilates studio with a cream arched doorway, wood floor, warm morning light and flowers on a pedestal",
    "a serene yoga studio at golden hour, large windows with sheer curtains, wood floor, a yoga mat and cork block, warm glow",
    # high-end gym
    "a luxury boutique gym with moody warm lighting, a rack of black dumbbells, cable machines in the background and a dark modern interior with spotlights",
    "an upscale gym with a squat rack and stacked weight plates, warm industrial lighting, exposed brick and a large mirror",
    "a high-end hotel gym with a floor-to-ceiling window and a city skyline at golden hour, benches and treadmills, warm glow",
    "a sleek private gym with black weight machines, warm accent lighting, polished concrete floor and a full-length mirror",
]

# v2: STANDING full-body ONLY (seated/kneeling/over-shoulder composited badly + gave claw hands).
POSES = [
    "standing straight facing the mirror",
    "standing with her weight on one hip, hip popped slightly",
    "standing turned slightly to the side to show her figure, glancing at the mirror",
    "standing tall and relaxed with one hand resting on her hip",
    "standing casually with feet together, soft candid expression",
    "standing angled a little to the side, chin slightly down",
]

def make_prompt(outfit, setting, pose):
    return (f"Using the exact woman from the reference image, create a full-body VERTICAL mirror "
            f"selfie. She is {pose}. {EYE} She wears {outfit}. Setting: {setting}. {STYLE}")

def build_bank(n=30, seed_offset=0):
    """Deterministic spread across settings x poses x outfits."""
    combos = []
    i = 0
    while len(combos) < n:
        s = SETTINGS[i % len(SETTINGS)]
        p = POSES[(i // len(SETTINGS)) % len(POSES)]
        o = OUTFITS[i % len(OUTFITS)]
        combos.append((i + 1 + seed_offset, make_prompt(o, s, p)))
        i += 1
    return combos

def gen_one(idx, prompt):
    try:
        res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
            arguments={"prompt": prompt, "image_urls": [REF],
                       "num_images": 1, "image_size": "portrait_16_9"})
        url = res["images"][0]["url"]
        fn = os.path.join(OUT, f"slide1_{idx:02d}.jpg")
        urllib.request.urlretrieve(url, fn)
        return (idx, fn, url, None)
    except Exception as e:
        return (idx, None, None, str(e))

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    bank = build_bank(n, start)
    json.dump({i: p for i, p in bank}, open(os.path.join(OUT, "prompts_used.json"), "w"), indent=1)
    print(f"Generating {len(bank)} slide-1 images (start idx {start+1})...", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(gen_one, i, p): i for i, p in bank}
        for f in as_completed(futs):
            idx, fn, url, err = f.result()
            done += 1
            if err:
                print(f"[{done}/{len(bank)}] idx {idx} FAILED: {err[:120]}", flush=True)
            else:
                print(f"[{done}/{len(bank)}] idx {idx} -> {os.path.basename(fn)}", flush=True)
    print("BATCH DONE", flush=True)
