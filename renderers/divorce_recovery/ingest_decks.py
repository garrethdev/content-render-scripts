#!/usr/bin/env python3
"""
ingest_decks.py: turn Divorce Recovery writer decks into rows of
public.divorce_recovery_carousel, ready for render_divorce_recovery.py.

Copy only ever comes from the n8n writer ("Divorce Recovery: carousel copy writer",
MLp2no3qGDAcDuLD).

--decks N asks the writer for N decks. A run takes about three and a half minutes, and
n8n cloud closes a web call after about two, so the writer does not send the decks back.
It answers at once, and when it finishes it inserts the rows itself (same mapping as
deck_to_row below) under the batch name this script sent. The script waits for those
rows, then gives each one a song from music_library.

--from-file inserts a saved writer response (for example the Collect Decks output of a
run started by hand in n8n), with the song, exactly as before.

Decks the writer flags needs_review go in with render_status='review' so they are
not rendered until someone looks at them; everything else is render_status='pending'.

Music: an active music_library song, preferring the 'divorce_set' mood tag, then
breakup / vindication / liberation moods; least used in this table first, seeded by
the batch so a rerun picks the same songs. Stored as 'Artist - Title'.

Usage
-----
  python3 ingest_decks.py --decks 5                     # writer writes 5 rows, then songs
  python3 ingest_decks.py --decks 5 --hold              # same, rows start on posting_status Hold
  python3 ingest_decks.py --decks 10 --batch dr-launch-1
  python3 ingest_decks.py --from-file writer_run.json   # insert a saved writer response
  python3 ingest_decks.py --from-file writer_run.json --dry-run   # print rows, insert nothing

Env: DR_WRITER_URL (default the production webhook), DR_WRITER_WAIT (seconds to wait for
the writer's rows, default 900), plus the Supabase key that render_divorce_recovery.py uses.
"""

import argparse
import datetime as dt
import json
import os
import random
import sys
import time

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


WRITER_WAIT = int(env.get("DR_WRITER_WAIT", "900"))
ROW_FIELDS = "carousel_id,slide_1,sender_name,his_text,render_status,music,slide_count"


def batch_rows(batch):
    base, h = _sb()
    r = requests.get(f"{base}/{TABLE}", headers=h, timeout=30,
                     params={"select": ROW_FIELDS, "batch": f"eq.{batch}", "order": "carousel_id"})
    r.raise_for_status()
    return r.json()


def call_writer(n, batch, hold=False):
    """Start a writer run and wait for the rows it inserts under this batch.
    The writer inserts all of a run's rows in one request, so the first new rows are the whole run."""
    before = {r["carousel_id"] for r in batch_rows(batch)}
    r = requests.post(WRITER_URL, json={"decks": n, "save": True, "batch": batch, "hold": hold}, timeout=60)
    r.raise_for_status()
    print(f"writer started for {n} deck(s), batch {batch}; waiting for its rows (about 4 minutes)")
    deadline = time.time() + WRITER_WAIT
    while time.time() < deadline:
        time.sleep(15)
        rows = [x for x in batch_rows(batch) if x["carousel_id"] not in before]
        if rows:
            if len(rows) < n:
                print(f"note: the writer saved {len(rows)} of {n} deck(s); a deck with missing copy is not saved")
            return rows
    raise SystemExit(f"No rows for batch {batch} after {WRITER_WAIT}s. Check the run in n8n "
                     f"(workflow MLp2no3qGDAcDuLD); nothing was inserted by this script.")


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


MIN_SLIDES, MAX_SLIDES = 6, 9


def deck_to_row(deck, batch, music):
    """One table row per deck. A deck has 6 to 9 slides: the hook, his text, then the
    story slides. Every row carries slide_3 to slide_9 (None past the last slide), so a
    batch with decks of different lengths still inserts in one request."""
    s = {int(x["n"]): x for x in deck["slides"]}
    n = max(s)
    if not MIN_SLIDES <= n <= MAX_SLIDES or sorted(s) != list(range(1, n + 1)):
        raise SystemExit(f"Deck {deck.get('deck_index')}: slides must run 1 to N with N from "
                         f"{MIN_SLIDES} to {MAX_SLIDES}, got {sorted(s)}")
    problems = deck.get("problems") or []
    story = {f"slide_{k}": (s[k].get("text") if k in s else None) for k in range(3, MAX_SLIDES + 1)}
    return {
        "deck": deck,
        "hook_text": s[1].get("text"),
        "slide_1": s[1].get("text"),
        "slide_2": s[2].get("her_line"),
        **story,
        "slide_count": n,
        "sender_name": s[2].get("sender_name"),
        "message_time": s[2].get("time"),
        "his_text": s[2].get("his_text"),
        "caption": s[n].get("caption") or deck.get("caption"),
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
    ap.add_argument("--dry-run", action="store_true", help="with --from-file: print the rows, insert nothing")
    ap.add_argument("--hold", action="store_true", help="with --decks: rows start on posting_status Hold")
    args = ap.parse_args()

    if args.decks:
        if args.dry_run:
            raise SystemExit("--dry-run needs --from-file: with --decks the writer inserts the rows itself.")
        saved = call_writer(max(1, min(10, args.decks)), args.batch, args.hold)
        songs = pick_songs(len(saved), args.batch)
        base, h = _sb()
        for row, music in zip(saved, songs):
            r = requests.patch(f"{base}/{TABLE}", json={"music": music}, timeout=30,
                               params={"carousel_id": f"eq.{row['carousel_id']}"},
                               headers={**h, "Content-Type": "application/json", "Prefer": "return=minimal"})
            r.raise_for_status()
            print(f"[{row['render_status']}] {row['carousel_id']} ({row.get('slide_count')} slides) "
                  f"{row['slide_1']!r} | {row['sender_name']}: {str(row['his_text'])[:60]}... | {music}")
        print(f"{len(saved)} row(s) in batch {args.batch}: {', '.join(x['carousel_id'] for x in saved)}")
        return

    data = json.load(open(args.from_file))
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
