"""Hook writing (Chris Chung framework, health/weight-loss oriented).

Proven hook mechanisms cloned from @jessicas_tt analysis:
  - Quoted Objection ("jealous friend"): a skeptical line in someone else's voice
  - POV call-out: "pov: your cravings finally went quiet"
  - Open loop / curiosity: "this is what actually stops the cravings..."
  - Reframe (health as freedom/self-love, not restriction)
  - Outcome + mechanism: "what i eat to stop the food noise"

Hard compliance filter: NOTHING GLP/peptide/drug-brand may appear in a hook (keep it lifestyle, not pharma).
"""
import re, random
from . import config, openrouter

# ---- compliance: terms that must never appear in a burned hook ----
BANNED = [
    "glp", "glp-1", "glp1", "peptide", "peptides", "semaglutide", "tirzepatide", "retatrutide",
    "ozempic", "wegovy", "mounjaro", "zepbound", "saxenda", "injection", "injectable",
]
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(b) for b in BANNED) + r")\b", re.IGNORECASE)

def has_banned(text):
    return bool(_BANNED_RE.search(text or ""))

def scrub(text):
    """Final safety net: strip banned terms and tidy whitespace (used before burning)."""
    return re.sub(r"\s{2,}", " ", _BANNED_RE.sub("", text or "")).strip(" ,-").strip()

_BASE = (
    "You write ONE short scroll-stopping hook overlay for a HEALTH / WEIGHT-LOSS short. "
    "Orient it to health and weight-loss outcomes: cravings, food noise, appetite, fullness, energy, weight, "
    "metabolism, bloating, sleep, inflammation — everyday lifestyle language, never clinical. "
    "4-9 words. lowercase is fine. No hashtags. No em dashes, no ampersands. "
    "NEVER mention GLP-1, peptides, semaglutide, tirzepatide, ozempic, wegovy, mounjaro, zepbound, or any "
    "drug/injection/medication name. Keep it lifestyle, not pharma."
)

# Chris Chung mechanisms. 'objection' (Jealous Friend) is the proven top performer -> weighted heaviest.
STYLE_PROMPTS = {
    "objection": ("Write it as a QUOTED OBJECTION - a skeptical, doubting, or jealous line in someone ELSE'S "
                  "voice (a hater or friend), e.g. i could never eat like that / how are you eating that much "
                  "and losing weight / do you always eat like this. It is the viewer's own doubt in another's mouth."),
    "openloop":  ("Write it as an OPEN LOOP ending in '...' that teases a reveal, "
                  "e.g. this is what actually stops the cravings... / the real reason you're always hungry..."),
    "reframe":   ("Write it as a REFRAME that frames health as freedom / self-love / maturity, not restriction, "
                  "e.g. this is what food freedom looks like / this is what finally feeling full feels like."),
    "process":   ("Write it as an OUTCOME + mechanism line, "
                  "e.g. what i eat to stop the food noise / what i changed to kill the 3pm crash."),
    "pov":       ("Write it as a POV call-out that qualifies the tribe, "
                  "e.g. pov: your cravings finally went quiet / pov: you stopped eating your feelings."),
}
# ~50-clip mix: heavy on the Jealous Friend winner, POV kept a minority.
STYLE_MIX = (["objection"] * 20 + ["openloop"] * 8 + ["reframe"] * 8 + ["process"] * 8 + ["pov"] * 6)

def _sanitize(text):
    line = text.strip().splitlines()[0] if text.strip() else ""
    line = re.split(r"\s*\(?\s*note:", line, flags=re.IGNORECASE)[0]
    # drop ALL double quotes (models leave stray/unbalanced ones), tidy spacing
    line = line.replace('"', "").replace("“", "").replace("”", "")
    line = line.replace("—", "").replace("&", "and")
    return re.sub(r"\s{2,}", " ", line).strip()

def _fallback(title):
    base = scrub((title or "watch this").split("#")[0]).strip().rstrip("?.!").lower()
    return base or "you need to see this"

def gen_hook(title, show, emoji=False, style="objection"):
    """One hook in a chosen Chris Chung mechanism. Retries if a banned term slips in; scrubs as last resort."""
    emoji_line = ("Add exactly ONE relevant emoji at the very end."
                  if emoji else "Do not use any emoji.")
    style_line = STYLE_PROMPTS.get(style, STYLE_PROMPTS["objection"])
    prompt = f"{_BASE}\n{style_line}\n{emoji_line}\nBase it loosely on this clip from '{show}'. Title: \"{title}\".\nReturn ONLY the hook text."
    for _ in range(2):
        try:
            reply = openrouter.chat(config.HOOK_MODEL, [{"role": "user", "content": prompt}],
                                    max_tokens=40, temperature=0.9)
            hook = _sanitize(reply)
        except Exception as e:
            print("   hook fail, fallback:", e)
            return _fallback(title)
        if hook and not has_banned(hook):
            return hook
        prompt += "\nThat used a banned pharma/drug term. Rewrite with NONE of those words."
    return scrub(hook) or _fallback(title)
