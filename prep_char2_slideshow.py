#!/usr/bin/env python3
"""Prep new Character 2 slideshow rows (2BA) for the scheduler — music + caption + approval.

Targets the NEW, not-yet-published Character 2 rows in ba_2slide_content (the batch the
slideshow chat inserts): posting_status IS NULL and final_video present. For each row it:
  - assigns an ethereal-pool track (Indila removed) round-robin -> suggested_ig_music
    (stored as "Artist - Title" that resolves in music_library)
  - writes a Universal-Caption-Maker caption (raw first-person BA testimony, 2 paragraphs,
    3 safe hashtags, no drug names / medical claims) if caption is empty
  - sets gatekeep_status='approved', character='Character 2'
  - leaves scheduler_ready=false and all scheduling columns NULL (release is a separate step)

Run it after the slideshow chat inserts its rows (idempotent — skips already-prepped fields):
  python prep_char2_slideshow.py [--batch <batch>] [--key <SUPABASE_SECRET_KEY>]
"""
import json, os, sys, urllib.request, urllib.parse

SB = os.environ.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co")
KEY = os.environ.get("CAROUSEL_SUPABASE_SECRET_KEY")
if "--key" in sys.argv:
    KEY = sys.argv[sys.argv.index("--key") + 1]
if not KEY:
    sys.exit("Provide the Supabase key: --key <KEY> or export CAROUSEL_SUPABASE_SECRET_KEY")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY}
TABLE = "ba_2slide_content"

# ethereal pool, Indila removed, only tracks that resolve in music_library
MUSIC = ["Sade - I Couldn't Love You More", "Enya - Caribbean Blue", "Massive Attack - Angel",
         "Madonna - Frozen", "Ghost - Mary On A Cross", "Cortex - Huit Octobre 1971",
         "AURORA - Runaway", "Lady Gaga - Bloody Mary", "Joe Strummer - Mondo Bongo",
         "FC Kahuna - Hayling", "Fairouz - Wahdon"]

CAP = [
 "I spent years avoiding every mirror in the house. Getting dressed meant whatever still fit, not whatever I liked, and I planned my whole day around not being seen.\n\nDown the weight now and I put on something off the regular rack this week and it just fit. I keep catching my reflection and doing a double take. I don't scan a room for the safe seat anymore.\n\n#weightlosstransformation #beforeandafter #glowup",
 "For the longest time I sat out of the photos, the pool days, all of it, and told everyone I just didn't feel like it. Really I just didn't want to be seen.\n\nDifferent story now. I'm in the front of the pictures and I don't delete a single one. Tried on old jeans and they fell off me. I don't even recognize the woman who used to hide.\n\n#transformation #realresults #weightlossjourney",
 "Stairs used to leave me winded halfway up and I'd play it off like I forgot something at the bottom. I'd made peace with that just being my life.\n\nNow I chase my kids around the yard and I'm the one who wants to keep going. Booked the trip, packed the swimsuit, no cover up. It still catches me off guard how different it feels.\n\n#momtransformation #beforeandafter #glowup"]


def rest(path, method="GET", body=None):
    hd = dict(H); data = None
    if body is not None:
        hd["Content-Type"] = "application/json"; data = json.dumps(body).encode()
    req = urllib.request.Request(SB + "/rest/v1/" + path, data=data, method=method, headers=hd)
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode(); return json.loads(t) if t else None


def main():
    batch = None
    if "--batch" in sys.argv:
        batch = sys.argv[sys.argv.index("--batch") + 1]
    flt = "character=eq.Character 2&posting_status=is.null&final_video=not.is.null"
    if batch:
        flt += f"&batch=eq.{batch}"
    rows = rest(f"{TABLE}?{urllib.parse.quote(flt, safe='=&.*')}&select=carousel_id,caption,suggested_ig_music&order=carousel_id")
    print(f"{len(rows)} new Character 2 slideshow rows to prep")
    for i, r in enumerate(rows):
        patch = {"gatekeep_status": "approved", "character": "Character 2"}
        if not (r.get("suggested_ig_music") or "").strip():
            patch["suggested_ig_music"] = MUSIC[i % len(MUSIC)]
        if not (r.get("caption") or "").strip():
            patch["caption"] = CAP[i % len(CAP)]
        rest(f"{TABLE}?carousel_id=eq.{urllib.parse.quote(r['carousel_id'])}", "PATCH", patch)
        print(f"  prepped {r['carousel_id']}")
    print("DONE — rows left at scheduler_ready=false; flip when released.")


if __name__ == "__main__":
    main()
