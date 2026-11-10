#!/usr/bin/env python3
"""
ingest_decks.py: turn Divorce Recovery writer decks into rows of
public.divorce_recovery_carousel, ready for render_divorce_recovery.py.

Copy only ever comes from the n8n writer ("Divorce Recovery: carousel copy writer",
MLp2no3qGDAcDuLD). This script calls its webhook (or reads a saved response), then
inserts one row per deck with the slide text, his message, the caption, and a song
picked from music_library.

Decks the writer flags needs_review go in with render_status='review' so they are
not rendered until someone looks at them; everything else is render_status='pending'.

Music: an active music_library song, preferring the 'divorce_set' mood tag, then
breakup / vindication / liberation moods; least used in this table first, seeded by
the batch so a rerun picks the same songs. Stored as 'Artist - Title'.

Usage
-----
  python3 ingest_decks.py --decks 5                     # call the writer, insert 5 rows
  python3 ingest_decks.py --decks 5 --dry-run           # call the writer, print rows only
  python3 ingest_decks.py --from-file writer_run.json   # insert a saved writer response
  python3 ingest_decks.py --decks 10 --batch dr-launch-1

Env: DR_WRITER_URL (default the production webhook), plus the Supabase key that
render_divorce_recovery.py uses.
"""

import argparse
import datetime as dt
import json
import os
import random
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import env  # noqa: E402

WRITER_URL = env.get("DR_WRITER_URL", "https://czed.app.n8n.cloud/webhook/divorce-recovery-copy-9c4e1f7a2b6d")
SUPABASE_PROJECT_REF = "qlcmgxgwpzmiebzxflai"
TABLE = "divorce_recovery_carousel"
MUSIC_FIRST = ("divorce_set",)
MUSIC_FIT = ("breakup", "vindication", "liberation", "heartbreak", "walking-away", "melancholic",
             "reflective", "wistful", "empowered", "empowerment", "triumphant")


def _sb():
    ref = env.get("CAROUSEL_SUPABASE_PROJECT", SUPABASE_PROJECT_REF)
    key = (env.get("CAROUSEL_SUPABASE_SECRET_KEY") or env.get("SUPABASE_SERVICE_KEY")
           or env.require("SUPABASE_ANON_KEY"))
    return f"https://{ref}.supabase.co/rest/v1", {"apikey": key, "Authorization": f"Bearer {key}"}


def call_writer(n):
    r = requests.post(WRITER_URL, json={"decks": n}, timeout=600)
    r.raise_for_status()
    data = r.json()
    if not data.get("decks"):
        raise SystemExit(f"Writer returned no decks: {json.dumps(data)[:300]}")
    return data


def pick_songs(n, seed):
    base, h = _sb()
    r = requests.get(f"{base}/music_library", headers=h, timeout=30,
                     params={"select": "artist,title,mood_tags,usage_count", "is_active": "eq.true"})
    r.raise_for_status()
    songs = r.json()
    first = [s for s in songs if set(s.get("mood_tags") or []) & set(MUSIC_FIRST)]
    fit = [s for s in songs if s not in first and set(s.get("mood_tags") or []) & set(MUSIC_FIT)]
    r = requests.get(f"{base}/{TABLE}", headers=h, timeout=30, params={"select": "music", "music": "not.is.null"})
    r.raise_for_status()
    used = {}
    for row in r.json():
        used[row["music"]] = used.get(row["music"], 0) + 1
    label = lambda s: f"{s['artist']} - {s['title']}"
    rng = random.Random(seed)
    picks = []
    for _ in range(n):
        pool = list(first) + list(fit)
        rng.shuffle(pool)
        # least used in this lane, then the divorce_set songs, then least used overall
        pool.sort(key=lambda s: (used.get(label(s), 0), s not in first, s.get("usage_count") or 0))
        choice = label(pool[0])
        used[choice] = used.get(choice, 0) + 1
        picks.append(choice)
    return picks


def deck_to_row(deck, batch, music):
    s = {x["n"]: x for x in deck["slides"]}
    problems = deck.get("problems") or []
    return {
        "deck": deck,
        "hook_text": s[1].get("text"),
        "slide_1": s[1].get("text"),
        "slide_2": s[2].get("her_line"),
        "slide_3": s[3].get("text"),
        "slide_4": s[4].get("text"),
        "slide_5": s[5].get("text"),
        "slide_6": s[6].get("text"),
        "sender_name": s[2].get("sender_name"),
        "message_time": s[2].get("time"),
        "his_text": s[2].get("his_text"),
        "caption": s[6].get("caption") or deck.get("caption"),
        "music": music,
        "writer_problems": problems or None,
        "render_status": "review" if deck.get("needs_review") or problems else "pending",
        "status": "scripted",
        "batch": batch,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--decks", type=int, help="how many decks to ask the writer for (1 to 10)")
    src.add_argument("--from-file", help="a saved writer response (JSON with a decks list)")
    ap.add_argument("--batch", default="dr-" + dt.datetime.now().strftime("%Y%m%d-%H%M"))
    ap.add_argument("--dry-run", action="store_true", help="print the rows, insert nothing")
    args = ap.parse_args()

    data = json.load(open(args.from_file)) if args.from_file else call_writer(max(1, min(10, args.decks)))
    decks = data["decks"]
    songs = pick_songs(len(decks), args.batch)
    rows = [deck_to_row(d, args.batch, m) for d, m in zip(decks, songs)]
    for r in rows:
        print(f"[{r['render_status']}] {r['slide_1']!r} | {r['sender_name']}: {str(r['his_text'])[:60]}... | {r['music']}")
    if args.dry_run:
        print(f"dry run: {len(rows)} row(s) not inserted")
        return
    base, h = _sb()
    r = requests.post(f"{base}/{TABLE}", json=rows, timeout=60,
                      headers={**h, "Content-Type": "application/json", "Prefer": "return=representation"})
    r.raise_for_status()
    ids = [x["carousel_id"] for x in r.json()]
    print(f"inserted {len(ids)} row(s) in batch {args.batch}: {', '.join(ids)}")


if __name__ == "__main__":
    main()
