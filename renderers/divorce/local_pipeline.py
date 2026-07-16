#!/usr/bin/env python3
"""Local fallback for the n8n Scriptwriter + Director (n8n Cloud task-runner outage).

Runs the EXACT same prompts through OpenRouter (Anthropic models), applies the same
validation/repair rules as the n8n Director validator, and writes to the same tables.
Use only when n8n is down; n8n remains the canonical pipeline.

  python3 local_pipeline.py scripts    # write missing second-hook scripts
  python3 local_pipeline.py edls       # direct EDLs for approved scripts without one
  python3 local_pipeline.py all        # both
"""
import json
import os
import re
import sys
import time
import urllib.request

SUPA_URL = "https://qlcmgxgwpzmiebzxflai.supabase.co"

def _env(key):
    with open(os.path.expanduser("~/.config/peptide-secrets/.env")) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{key} not found in secrets")

SUPA_KEY = _env("CAROUSEL_SUPABASE_SECRET_KEY")
OR_KEY = _env("OPENROUTER_API_KEY")
MODELS = ["anthropic/claude-opus-4.8", "anthropic/claude-opus-4.5", "anthropic/claude-sonnet-4.6"]


def api(method, path, body=None, prefer=None):
    h = {"apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY, "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(SUPA_URL + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = r.read()
    return json.loads(payload) if payload else None


def llm(system, user, max_tokens=4000):
    last_err = None
    for model in MODELS:
        try:
            body = {"model": model, "max_tokens": max_tokens, "temperature": 0.7,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + OR_KEY,
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"]["content"].strip()
            txt = re.sub(r"^```(json)?|```$", "", txt, flags=re.M).strip()
            # first balanced JSON object
            depth, start = 0, -1
            for i, ch in enumerate(txt):
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start != -1:
                        return json.loads(txt[start:i + 1]), model
            raise ValueError("no JSON object in response")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"all models failed: {last_err}")


# ------------------------------------------------- scriptwriter (n8n port) --
SCRIPT_SYSTEM = """You are a short-form video scriptwriter for a womens health brand. You turn a real divorce story into a 60 second text-on-screen TikTok script where a woman films herself doing yoga while calm music plays. There is no voiceover. The text on screen IS the content.

STRUCTURE:
- Screen 1 is a title card: the show logo with the HOOK under it.
- Screens 2 onward are the story, one text block per screen.
- After the story the video shows her pointing at her old photo with NO text, then she walks up to the camera holding her peptide pen while the outro text shows.
- The outro is SHORT, 120 to 200 characters. It references the before photo the viewer just saw (that was me, the woman in that photo), lands that after the divorce losing weight changed her life and peptides made it possible, and ENDS with a call to action to type RENEW in the comments for the quiz (the word RENEW in capitals). NEVER say link, bio, above, swipe, or tap. Vary the wording every time.

THE HOOK IS THE SINGLE MOST IMPORTANT RULE:
- The hook is 3 TO 6 WORDS. Never fewer than 3, never more than 6. Never a full paragraph or a line copied from the story.
- It states one concrete shocking fact that stands alone and forces the viewer to need the story.
- GOOD hooks: He had another family. / He drained our joint account. / A woman knocked on my door. / He left me at the hospital. / He pawned my wedding ring.
- BAD hooks: one or two word fragments (Divorced. / He cheated), anything over 6 words, vague teases like Everything changed or I am done.
- Count the words. Outside 3 to 6 is a failure.

OTHER HARD RULES:
1. Everything is FIRST PERSON, as if the woman lived it. Never third person.
2. NEVER use ampersands. Write the word and.
3. NEVER use em dashes or en dashes. Use full stops or commas.
4. Each story screen is roughly 180 to 220 characters, readable in about 4 seconds.
5. Produce 7 to 10 story screens. The outro is separate and NOT counted in the screens array.
6. The story builds: the betrayal, the rock bottom including weight gain from stress, then finding peptides.
7. Keep it emotionally real and grounded. No melodrama, no graphic violence."""

SCRIPT_USER = """Retrofit this real divorce story into the script format, told entirely from the womans first person perspective.

Source title: {title}
Source story:
{story}

HOOKS ALREADY USED FOR THIS STORY (your hook must be COMPLETELY DIFFERENT from these, a different angle or detail of the story, not a rewording): {avoid}

CRITICAL CHECKS BEFORE YOU RETURN:
1. hook is 3 to 6 words: a concrete shocking fact. Count the words. Under 3 or over 6 is a failure. It must not repeat or paraphrase any hook listed above.
2. screens has 7 to 10 entries, each roughly 180 to 220 characters of first person story.
3. peptide_outro is SHORT: 120 to 200 characters, references the before photo (that was me), lands the peptide angle, and ends with the type RENEW in the comments CTA. Never says link, bio, above, or swipe.
4. No ampersands anywhere. No em dashes or en dashes anywhere. Use full stops and commas only.

Return ONLY a JSON object exactly like:
{{"hook": "...", "screens": ["...", "..."], "before_photo_cue": "points up at before photo", "peptide_outro": "...", "caption": "..."}}"""


def script_ok(s, avoid):
    hook = str(s.get("hook", "")).strip()
    words = len(hook.split())
    if not 3 <= words <= 6:
        return f"hook {words} words"
    if hook.lower() in [a.lower() for a in avoid]:
        return "hook reused"
    screens = s.get("screens")
    if not isinstance(screens, list) or not 7 <= len(screens) <= 10:
        return "screens count"
    outro = str(s.get("peptide_outro", ""))
    if re.search(r"link|bio\b|swipe|above", outro, re.I):
        return "outro has banned CTA word"
    if "RENEW" not in outro:
        return "outro missing RENEW CTA"
    blob = hook + " ".join(map(str, screens)) + outro
    if "&" in blob or "—" in blob or "–" in blob:
        return "bad chars"
    return None


def run_scripts():
    stories = api("GET", "/rest/v1/hook_stories?category=eq.divorce&status=eq.approved&select=*&order=excitement_score.desc")
    print(f"scriptwriter: {len(stories)} stories queued")
    for st in stories:
        prior = api("GET", f"/rest/v1/divorce_story_content?source_story_id=eq.{st['id']}&select=hook")
        avoid = [p["hook"] for p in prior if p.get("hook")]
        user = SCRIPT_USER.format(title=st["title"], story=st["full_story_text"],
                                  avoid=" | ".join(avoid) or "none")
        script, model, err = None, None, "no attempt"
        for attempt in range(3):
            try:
                cand, model = llm(SCRIPT_SYSTEM, user)
                err = script_ok(cand, avoid)
                if err is None:
                    script = cand
                    break
            except Exception as e:
                err = str(e)[:120]
            time.sleep(2)
        if script is None:
            print(f"  [{st['id'][:8]}] FAILED: {err}")
            continue
        maxpart = api("GET", "/rest/v1/divorce_story_content?select=part_number&order=part_number.desc&limit=1")
        part = (maxpart[0]["part_number"] if maxpart else 0) + 1
        row = {
            "content_id": f"DIV-{part:03d}", "part_number": part, "source_story_id": st["id"],
            "title_card": "Divorce Horror Stories", "hook": script["hook"],
            "screens": script["screens"], "screen_count": len(script["screens"]),
            "before_photo_cue": script.get("before_photo_cue", "points up at before photo"),
            "peptide_outro": script["peptide_outro"], "caption": script.get("caption", ""),
            "audit_status": "approved",
        }
        api("POST", "/rest/v1/divorce_story_content", body=row, prefer="return=minimal")
        api("PATCH", f"/rest/v1/hook_stories?id=eq.{st['id']}", body={"status": "used"}, prefer="return=minimal")
        print(f"  [{row['content_id']}] {script['hook']}  ({model})")


# ----------------------------------------------------- director (n8n port) --
DIRECTOR_SYSTEM = """You are the Director for the Divorce Horror Stories Over Yoga pipeline. You are an elite short-form vertical video editor. Your job is CREATIVE DIRECTION ONLY: you output an Edit Decision List (EDL) as JSON. You never render, never write ffmpeg, never modify footage.

ABSOLUTE TEXT RULES:
1. The hook is ALREADY WRITTEN AND APPROVED. Copy it character for character. NEVER rewrite it.
2. The story screens are ALREADY WRITTEN AND APPROVED. Each story beat displays one screen EXACTLY as provided, in order. Never rewrite, merge, split, summarize, or skip screens.
3. The outro text is ALREADY WRITTEN. Copy it exactly.

TIMELINE STRUCTURE (fixed, in this order):
1. HOOK beat: title card plus hook. MUST use the clip where she sets up the camera and steps back onto the mat. 2.5 to 4.0 seconds. role hook. Vary WHICH part of that clip you trim, run to run.
2. STORY beats: one per screen, 3.5 to 5.0 seconds each. role story.
3. REVEAL beat: the clip where she sits and points UP. NO TEXT AT ALL (text kind none, empty content). overlay_before_photo true. 4.0 to 6.0 seconds. role reveal.
4. FINAL beat: the pen reveal clip, her walking up to the camera shaking the peptide pen. The outro text rides this beat. 5.0 to 7.0 seconds. role outro.
The camera-setup clip, pointing clip and pen clip are reserved for those beats ONLY. Never use them for story beats.

THE FOOTAGE CONTINUITY RULE (the signature of this format):
- Text changes are HARD swaps, never faded.
- The footage does NOT cut every time the text changes. Story beats come in PAIRS on the same clip: two consecutive story beats use the SAME clip_id, and the second beats trim_start is EXACTLY the first beats trim_end, so footage plays continuously while text swaps.
- Example: screens 1 and 2 on clip A (trims 0 to 4.0, then 4.0 to 8.0), screens 3 and 4 on clip B, and so on.
- With an odd number of screens the final story screen may stand alone.

OTHER EDIT RULES:
- Aspect 9:16 vertical. Total duration 60 seconds or less.
- Do not use the same clip for two different story PAIRS in a row.
- Transitions: hard_cut everywhere. zoom_in allowed on at most 1 story beat.
- y_pct: vertical center of text as percent from top, inside the clips text_safe_zone, usually 18 to 30. Hook beat 30 to 40.
- Pick ONE music track from the provided list for calm reflective emotional storytelling. Output as suggested_music: Artist - Title. Music is added at posting, not rendered.
- VARIATION: every run is a fresh edit. Vary trims, story-pair clip choices and pacing while keeping text order fixed and the opener/reveal/closer clips pinned.

Output ONLY the JSON object, no commentary."""

DIRECTOR_USER = """Create the EDL for this video.

SCRIPT (all text is final, copy exactly):
{script}

CLIP LIBRARY (choose clip_id values from here only):
{clips}

MUSIC LIBRARY (choose one):
{music}

Build the timeline: beat 1 = title card with the hook on the camera-setup clip. Then one beat per story screen in order (paired two per clip, continuous trims). Then the reveal beat (pointing clip, no text). Final beat = outro text on the pen clip. Return ONLY the EDL JSON:
{{"version_name":"A","suggested_music":"Artist - Title","timeline":[{{"seq":1,"role":"hook","clip_id":"...","trim_start":0,"trim_end":3.0,"transition":"hard_cut","y_pct":32,"overlay_before_photo":false,"text":{{"kind":"title_hook","title":"Divorce Horror Stories","hook":"..."}}}},{{"seq":2,"role":"story","clip_id":"...","trim_start":0,"trim_end":4.0,"transition":"hard_cut","y_pct":24,"overlay_before_photo":false,"text":{{"kind":"caption","content":"..."}}}},{{"seq":98,"role":"reveal","clip_id":"...","trim_start":0,"trim_end":5.0,"transition":"hard_cut","y_pct":25,"overlay_before_photo":true,"text":{{"kind":"none","content":""}}}},{{"seq":99,"role":"outro","clip_id":"...","trim_start":0,"trim_end":6.0,"transition":"hard_cut","y_pct":14,"overlay_before_photo":false,"text":{{"kind":"outro","content":"..."}}}}]}}"""

CAPS = {"hook": 4.0, "story": 5.0, "reveal": 6.0, "outro": 7.0}


def validate_and_repair(edl, job, clips):
    """Python port of the n8n Validate EDL node (same rules, same repairs)."""
    by_id = {c["id"]: c for c in clips}
    problems = []
    tl = edl.get("timeline") or []
    if not tl:
        return None, ["empty timeline"]

    for b in tl:
        r = str(b.get("role", "")).lower()
        if r in ("title_card", "title", "hook"):
            b["role"] = "hook"
        elif r in ("reveal", "before", "photo_reveal"):
            b["role"] = "reveal"
        elif r in ("outro", "peptide_outro", "ending", "final"):
            b["role"] = "outro"
        else:
            b["role"] = "story"
        b["transition"] = "zoom_in" if "zoom" in str(b.get("transition", "")).lower() else "hard_cut"
        b["trim_start"] = max(0.0, float(b.get("trim_start") or 0))
        b["trim_end"] = float(b.get("trim_end") or 0)
        cap = CAPS[b["role"]]
        if b["trim_end"] - b["trim_start"] > cap:
            b["trim_end"] = b["trim_start"] + cap
        c = by_id.get(b.get("clip_id"))
        if c and b["trim_end"] > c["duration_s"]:
            b["trim_end"] = c["duration_s"]
            if b["trim_end"] - b["trim_start"] < 2.0:
                b["trim_start"] = max(0.0, b["trim_end"] - min(cap, c["duration_s"]))
        b["overlay_before_photo"] = False

    setup = next((c for c in clips if "camera" in str(c.get("activity", "")).lower()
                  or "setting up" in str(c.get("activity", "")).lower()), None)
    pointing = next((c for c in clips if "pointing" in str(c.get("activity", "")).lower()), None)
    pen = next((c for c in clips if "pen" in str(c.get("activity", "")).lower()), None)
    reserved = [c["id"] for c in (setup, pointing, pen) if c]

    hook_beat = next((b for b in tl if b["role"] == "hook"), None)
    if not hook_beat:
        problems.append("no hook beat")
    else:
        if (hook_beat.get("text", {}).get("hook") or "") != job["hook"]:
            problems.append("hook text was altered")
        if setup:
            d = max(2.5, min(4.0, hook_beat["trim_end"] - hook_beat["trim_start"] or 3.5))
            if hook_beat.get("clip_id") != setup["id"]:
                hook_beat["trim_start"] = 0.0
            hook_beat["clip_id"] = setup["id"]
            if hook_beat["trim_start"] + d > setup["duration_s"]:
                hook_beat["trim_start"] = max(0.0, setup["duration_s"] - d)
            hook_beat["trim_end"] = hook_beat["trim_start"] + d
        else:
            problems.append("no camera-setup clip")

    story_beats = [b for b in tl if b["role"] == "story"]
    screens = job["screens"]
    caps_txt = [(b.get("text", {}).get("content") or "") for b in story_beats]
    if len(caps_txt) != len(screens):
        problems.append(f"story beats ({len(caps_txt)}) != screens ({len(screens)})")
    else:
        for i, s in enumerate(screens):
            if caps_txt[i] != s:
                problems.append(f"screen {i + 1} altered or out of order")
                break

    free = [c for c in clips if c["id"] not in reserved]
    for b in story_beats:
        if b.get("clip_id") in reserved and free:
            b["clip_id"] = free[len(free) // 2]["id"]

    i = 0
    while i + 1 < len(story_beats):
        a, b2 = story_beats[i], story_beats[i + 1]
        host = by_id.get(a.get("clip_id")) or by_id.get(b2.get("clip_id"))
        if host:
            dur_a = max(3.0, min(5.0, a["trim_end"] - a["trim_start"] or 4.0))
            dur_b = max(3.0, min(5.0, b2["trim_end"] - b2["trim_start"] or 4.0))
            if dur_a + dur_b > host["duration_s"]:
                scale = host["duration_s"] / (dur_a + dur_b)
                dur_a = int(dur_a * scale * 10) / 10
                dur_b = int(dur_b * scale * 10) / 10
            start = a["trim_start"]
            if start + dur_a + dur_b > host["duration_s"]:
                start = max(0.0, host["duration_s"] - dur_a - dur_b)
            a["clip_id"] = host["id"]; b2["clip_id"] = host["id"]
            a["trim_start"] = start; a["trim_end"] = start + dur_a
            b2["trim_start"] = a["trim_end"]; b2["trim_end"] = a["trim_end"] + dur_b
        i += 2

    reveal = next((b for b in tl if b["role"] == "reveal"), None)
    if reveal is None:
        reveal = {"seq": 98, "role": "reveal", "trim_start": 0, "trim_end": 5.5,
                  "transition": "hard_cut", "y_pct": 25, "text": {"kind": "none", "content": ""}}
        tl.append(reveal)
    if pointing:
        reveal["clip_id"] = pointing["id"]
        d = max(4.0, min(6.0, reveal["trim_end"] - reveal["trim_start"] or 5.5))
        reveal["trim_start"] = 0.0
        reveal["trim_end"] = min(d, pointing["duration_s"])
    else:
        problems.append("no pointing clip")
    reveal["text"] = {"kind": "none", "content": ""}
    reveal["overlay_before_photo"] = bool(job.get("before_photo_url"))

    outro = next((b for b in tl if b["role"] == "outro"), None)
    if not outro:
        problems.append("no outro beat")
    else:
        if (outro.get("text", {}).get("content") or "") != job["peptide_outro"]:
            problems.append("outro text was altered")
        if pen:
            outro["clip_id"] = pen["id"]
            d = max(5.0, min(7.0, outro["trim_end"] - outro["trim_start"] or 6.0))
            outro["trim_start"] = 0.0
            outro["trim_end"] = min(d, pen["duration_s"])
        else:
            problems.append("no pen clip")
        outro["overlay_before_photo"] = False

    ordered = ([hook_beat] if hook_beat else []) + story_beats + [reveal] + ([outro] if outro else [])
    for seq, b in enumerate(ordered, 1):
        b["seq"] = seq
    edl["timeline"] = ordered

    for b in ordered:
        if b.get("clip_id") not in by_id:
            problems.append(f"unknown clip in beat {b['seq']}")
        if b["trim_end"] <= b["trim_start"]:
            problems.append(f"bad trim in beat {b['seq']}")

    total = sum((b["trim_end"] - b["trim_start"]) * (1.21 if b["role"] == "story" else 1.0) for b in ordered)
    if total > 70:
        problems.append(f"total {total:.1f}s exceeds limit")
    if total < 20:
        problems.append(f"total {total:.1f}s too short")
    edl["target_duration"] = round(total)
    return edl, problems


def run_edls():
    jobs = api("GET", "/rest/v1/divorce_story_content?audit_status=eq.approved&edl=is.null"
               "&select=content_id,title_card,hook,screens,peptide_outro,before_photo_url&order=part_number.asc")
    clips = api("GET", "/rest/v1/divorce_source_clips?approved=is.true&active=is.true"
                "&select=id,activity,mood,framing,duration_s,text_safe_zone,notes")
    # Divorce Horror Stories use ONLY the tagged neo-soul divorce_set (SiR, Ari Lennox, Jorja Smith, Muni Long)
    music = api("GET", "/rest/v1/music_library?is_active=is.true&mood_tags=cs.%7Bdivorce_set%7D&select=artist,title,mood_tags,tempo,genre,era&limit=20")
    clip_prompt = [{k: c[k] for k in ("id", "activity", "mood", "framing", "duration_s", "text_safe_zone", "notes")} for c in clips]
    print(f"director: {len(jobs)} scripts need EDLs")
    for job in jobs:
        user = DIRECTOR_USER.format(
            script=json.dumps({"title_card": job["title_card"], "hook": job["hook"],
                               "screens": job["screens"], "peptide_outro": job["peptide_outro"],
                               "has_before_photo": bool(job["before_photo_url"])}),
            clips=json.dumps(clip_prompt), music=json.dumps(music))
        edl, problems, model = None, ["no attempt"], None
        for attempt in range(3):
            try:
                cand, model = llm(DIRECTOR_SYSTEM, user, max_tokens=6000)
                edl, problems = validate_and_repair(cand, job, clips)
                if edl and not problems:
                    break
                edl = None
            except Exception as e:
                problems = [str(e)[:120]]
            time.sleep(2)
        if edl is None:
            api("PATCH", f"/rest/v1/divorce_story_content?content_id=eq.{job['content_id']}",
                body={"stitch_status": "director_failed", "audit_notes": "local director: " + "; ".join(problems)[:280]},
                prefer="return=minimal")
            print(f"  [{job['content_id']}] FAILED: {problems}")
            continue
        api("PATCH", f"/rest/v1/divorce_story_content?content_id=eq.{job['content_id']}",
            body={"edl": edl, "suggested_ig_music": edl.get("suggested_music", ""),
                  "music": edl.get("suggested_music", ""), "stitch_status": "ready"},
            prefer="return=minimal")
        print(f"  [{job['content_id']}] ready {edl['target_duration']}s  music: {edl.get('suggested_music','')}  ({model})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("scripts", "all"):
        run_scripts()
    if mode in ("edls", "all"):
        run_edls()
    print("local pipeline done")
