#!/usr/bin/env python3
"""Local matcher / Stage. Pulls clips ROUND-ROBIN from the curated, pre-graded source library
(status='library'), least-recently-used first, writes 3 compliant hooks each, rotates characters
(2/3/4), inserts queued jobs whose source points at the graded library file, and stamps
last_used_at. When all clips have been used it cycles back to the oldest. Usage: python3 queue_match.py [N]
"""
import sys, re, json, datetime, urllib.request, urllib.parse
import config, supa

N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
CB = config.SUPABASE_URL + "/storage/v1/object/public/viral-filler/characters/"
CHARS = [CB + "character-2.mp4", CB + "character-3.mp4", CB + "character-4.mp4"]
BAD = [r"\b(ozempic|wegovy|zepbound|mounjaro|saxenda|rybelsus|semaglutide|tirzepatide|retatrutide|liraglutide)\b",
       r"glp-?1|\bpeptide\b|the shot|injection",
       r"\b(cure[sd]?|heals?|reverses?|diabetes|insulin|melts? fat|prevents?)\b",
       r"\d{1,3}\s?% ?off|\.com|\bbuy\b|discount|use code|link in bio|\bdm me\b"]
def banned(h): return any(re.search(p, h, re.I) for p in BAD)

SYS = ("You write SHORT on-screen TEXT HOOKS for a brand-safe weight-loss / clean-eating filler "
       "video. Write every hook in THIRD PERSON about the woman in the video (she/her), never first "
       "person. Each hook max 12 words, sounds like a real caption. No drug or brand names, no "
       "medical claims, no selling, no ampersands. Return ONLY three distinct hooks, one per line, "
       "no numbering, no quotes.")

MODEL = "z-ai/glm-4.6"

def _openrouter(messages, max_tokens):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.9, "reasoning": {"enabled": False}}   # GLM-4.6 is a thinking model; skip thinking
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {config.OPENROUTER_KEY}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))["choices"][0]["message"].get("content")

def gen_hooks(about, angle):
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": f"about: {about or ''} | angle: {angle or ''}"}]
    txt = _openrouter(msgs, 400) or _openrouter(msgs, 1500) or ""   # retry w/ more tokens if thinking ate the budget
    lines = [re.sub(r'^["\'\s\d\.\)\-]+', '', l).strip(' "\'') for l in txt.splitlines()]
    lines = [l for l in lines if len(l) > 2 and not banned(l)]
    while len(lines) < 3:
        lines.append("She did not come this far to quit on herself now")
    return lines[:3]

def main(n=N):
    # round-robin over the curated, graded library: least-recently-used first (null last_used_at = never used)
    clips = supa.rest(f"filler_library?status=eq.library&select=aweme_id,url,handle,hook_angle,about,source_video_url"
                      f"&order=last_used_at.asc.nullsfirst&limit={n}") or []
    print(f"matching {len(clips)} library clips (round-robin, LRU) -> {len(clips)*3} jobs...")
    rows, used = [], []
    for c in clips:
        hooks = gen_hooks(c.get("about"), c.get("hook_angle"))
        src = c.get("source_video_url") or c["url"]          # graded library file (fallback to original url)
        for i in range(3):
            rows.append({"filler_aweme_id": c["aweme_id"], "source_url": src, "handle": c.get("handle"),
                         "hook_angle": c.get("hook_angle"), "about": c.get("about"), "hook": hooks[i],
                         "character_url": CHARS[i], "status": "queued"})
        used.append(str(c["aweme_id"]))
    if rows:
        supa.rest("viral_filler_content", "POST", rows, prefer="return=minimal")
        now = datetime.datetime.utcnow().isoformat() + "Z"   # stamp usage so next run picks the next-oldest (cycles)
        supa.rest("filler_library?aweme_id=in.(" + ",".join(used) + ")", "PATCH",
                  {"last_used_at": now}, prefer="return=minimal")
    print(f"queued {len(rows)} jobs from {len(used)} clips; last_used_at stamped (round-robin / reuse cycle).")

if __name__ == "__main__":
    main()
