#!/usr/bin/env python3
"""One-time repair: every outro must end with the Type RENEW quiz CTA
(never "link above" / "in my bio"). Rewrites peptide_outro via LLM, syncs the
EDL outro beat text, fixes any caption still pushing link-in-bio, and queues
the row for re-render."""
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
    raise SystemExit(f"{key} missing")

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


def llm(system, user):
    last = None
    for model in MODELS:
        try:
            body = {"model": model, "max_tokens": 1000, "temperature": 0.8,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                         data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + OR_KEY, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"]["content"].strip()
            txt = re.sub(r"^```(json)?|```$", "", txt, flags=re.M).strip()
            depth, start = 0, -1
            for i, ch in enumerate(txt):
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start != -1:
                        return json.loads(txt[start:i + 1])
            raise ValueError("no JSON")
        except Exception as e:
            last = e
    raise RuntimeError(str(last))


SYSTEM = """You edit the final on-screen line of short divorce-recovery videos for a womens health brand.
The line shows while she walks up to the camera holding her peptide pen, right after the viewer saw her before photo.
Rules:
- Keep the emotional first-person voice and the peptide angle of the original line.
- The line MUST end with a call to action telling the viewer to type RENEW in the comments to get the quiz. Vary the CTA wording naturally (examples: Type RENEW and I will send you the quiz I started with. / Comment RENEW for the exact quiz that started this. / Type RENEW below for the quiz.). The word RENEW in capitals must appear.
- NEVER say link, bio, above, swipe, or tap.
- 120 to 200 characters total. First person. No ampersands. No em or en dashes. Full stops and commas only."""

USER = """Original outro line:
{outro}

Original caption (fix ONLY if it mentions link or bio, otherwise return it unchanged):
{caption}

Return ONLY JSON: {{"peptide_outro": "...", "caption": "..."}}"""


def ok(o):
    if not (100 <= len(o) <= 220):
        return "length"
    if "RENEW" not in o:
        return "no RENEW"
    if re.search(r"link|bio\b|swipe|above", o, re.I):
        return "banned word"
    if "&" in o or "—" in o or "–" in o:
        return "bad chars"
    return None


def main():
    rows = api("GET", "/rest/v1/divorce_story_content?select=content_id,peptide_outro,caption,edl&order=part_number")
    print(f"fixing {len(rows)} outros")
    fixed = 0
    for r in rows:
        new = None
        for attempt in range(3):
            try:
                cand = llm(SYSTEM, USER.format(outro=r["peptide_outro"], caption=r["caption"] or ""))
                err = ok(cand.get("peptide_outro", ""))
                if err is None:
                    new = cand
                    break
                print(f"  [{r['content_id']}] retry: {err}")
            except Exception as e:
                print(f"  [{r['content_id']}] retry: {str(e)[:80]}")
            time.sleep(2)
        if new is None:
            print(f"  [{r['content_id']}] FAILED, left untouched")
            continue
        edl = r["edl"]
        for b in edl.get("timeline", []):
            if b.get("role") == "outro":
                b["text"] = {"kind": "outro", "content": new["peptide_outro"]}
        api("PATCH", f"/rest/v1/divorce_story_content?content_id=eq.{r['content_id']}",
            body={"peptide_outro": new["peptide_outro"], "caption": new.get("caption") or r["caption"],
                  "edl": edl, "stitch_status": "ready"},
            prefer="return=minimal")
        fixed += 1
        print(f"  [{r['content_id']}] ok: ...{new['peptide_outro'][-60:]}")
    print(f"fixed {fixed}/{len(rows)}")


if __name__ == "__main__":
    main()
