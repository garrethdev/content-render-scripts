#!/usr/bin/env python3
"""Make Story Wall rows from story_bank stories.

  python3 create_batch.py --batch sw-20261125 --stories 10993,13529,... [--dry-run]

For each story: the on-screen text (story_paragraph: one paragraph, title joined, Reddit tag
dropped, words unchanged), which must fit at 52 px or larger; the first sentence as hook_text;
a clip from quote_video_clips that is at least 8 s long (least used first, her face first, never
the same scene twice in a row; a blue clip and the white clip it came from are one scene); a
song from music_library tagged kitchen_quote_video (same quiet acoustic list), least used first.
Rows get content_id SW-NNN, the next free numbers. Each story is marked used in story_uses
(lane story_wall_video) so no other lane takes it.
"""
import argparse
import datetime as dt
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_story_wall as R  # noqa: E402

LANE = "story_wall_video"


def post(table, rows):
    url, h = R.service()
    r = requests.post(f"{url}/rest/v1/{table}", json=rows,
                      headers={**h, "Content-Type": "application/json", "Prefer": "return=representation"}, timeout=60)
    r.raise_for_status()
    return r.json()


def first_sentence(text):
    m = re.match(r"(.+?[.!?…])(\s|$)", text)
    return (m.group(1) if m else text).strip()[:200]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--stories", required=True, help="comma list of story_bank ids, in posting order")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env-file")
    a = ap.parse_args()
    if a.env_file:
        R.env.load_env(os.path.expanduser(a.env_file))
    ids = [int(x) for x in a.stories.split(",") if x.strip()]
    stories = {s["id"]: s for s in R.get("story_bank", select="id,title,text", id="in.(%s)" % ",".join(map(str, ids)))}
    used = {u["story_id"] for u in R.get("story_uses", select="story_id", status="in.(used,reserved)",
                                          story_id="in.(%s)" % ",".join(map(str, ids)))}
    if used & set(ids):
        raise SystemExit(f"already used by another lane: {sorted(used & set(ids))}")
    existing = R.get("story_wall_posts", select="content_id,clip_no,music")
    taken = {r["content_id"] for r in existing}
    clips = [c for c in R.get("quote_video_clips", is_active="eq.true", order="clip_no",
                              select="clip_no,face_visible,shirt_color,source_clip_no,usage_count,duration_s")
             if float(c["duration_s"]) >= R.LENGTH]
    clip_uses = {}
    for r in existing:
        clip_uses[r["clip_no"]] = clip_uses.get(r["clip_no"], 0) + 1
    songs = [f"{s['artist']} - {s['title']}" for s in R.get("music_library", select="artist,title", is_active="eq.true",
                                                            pillar_fit="cs.{kitchen_quote_video}", order="created_at")]
    song_uses = {}
    for r in existing:
        if r.get("music"):
            song_uses[r["music"]] = song_uses.get(r["music"], 0) + 1

    def scene(c):
        return c.get("source_clip_no") or c["clip_no"]

    n, rows, last_scene, last_song, run_scenes = 0, [], None, None, {}
    for sid in ids:
        text = R.story_paragraph(stories[sid])
        R.fit(text)  # raises if it does not fit at 52 px
        while True:
            n += 1
            cid = f"SW-{n:03d}"
            if cid not in taken:
                break
        pool = [c for c in clips if scene(c) != last_scene] or clips
        clip = min(pool, key=lambda c: (run_scenes.get(scene(c), 0), clip_uses.get(c["clip_no"], 0) + (c.get("usage_count") or 0),
                                        not c.get("face_visible"), c["clip_no"]))
        clip_uses[clip["clip_no"]] = clip_uses.get(clip["clip_no"], 0) + 1
        run_scenes[scene(clip)] = run_scenes.get(scene(clip), 0) + 1
        last_scene = scene(clip)
        fresh = [s for s in songs if s != last_song] or songs
        song = min(fresh, key=lambda s: (song_uses.get(s, 0), songs.index(s)))
        song_uses[song] = song_uses.get(song, 0) + 1
        last_song = song
        rows.append(dict(content_id=cid, batch=a.batch, story_id=sid, story_text=text, hook_text=first_sentence(text),
                         clip_no=clip["clip_no"], shirt_color=clip.get("shirt_color"), music=song))
    for r in rows:
        print(r["content_id"], r["story_id"], "clip", r["clip_no"], "|", r["music"], "|", len(r["story_text"].split()), "words |", r["hook_text"][:70])
    if a.dry_run:
        print("dry run: nothing saved")
        return
    post("story_wall_posts", rows)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    post("story_uses", [dict(story_id=r["story_id"], lane=LANE, status="used", run_id=a.batch, deck_ref=r["content_id"],
                             used_at=now) for r in rows])
    print(f"saved {len(rows)} rows and marked {len(rows)} stories used")


if __name__ == "__main__":
    main()
