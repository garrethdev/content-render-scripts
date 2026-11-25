"""Font and emoji pictures for the Kitchen Quote Video overlay, kept out of git.

First use downloads the 2026-11-24 renderer kit from storage (the same font and emoji the
21 live videos were rendered with) and unpacks the font and emoji into ./cache/.
An emoji that is not in the kit is fetched once from the same Apple set
(emoji-datasource-apple 15.1.2, 64 px) and kept in ./cache/emoji/.
"""
import io
import os
import tarfile
import urllib.request

from common import env

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = env.get("KQV_CACHE_DIR", os.path.join(HERE, "cache"))
EMOJI_DIR = os.path.join(CACHE, "emoji")
FONT = os.path.join(CACHE, "TikTokSans-Bold-opsz36.ttf")
KIT_PATH = "kitchen-character/kitchen-quote-video/renderer/kqv_renderer_2026-11-24.tgz"
EMOJI_CDN = "https://cdn.jsdelivr.net/npm/emoji-datasource-apple@15.1.2/img/apple/64/{}.png"


def _kit_url():
    sb = env.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co").rstrip("/")
    return f"{sb}/storage/v1/object/public/{KIT_PATH}"


def _unpack_kit():
    os.makedirs(EMOJI_DIR, exist_ok=True)
    data = urllib.request.urlopen(_kit_url(), timeout=60).read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            name = os.path.basename(m.name)
            if m.name.endswith(".ttf"):
                dst = FONT
            elif "/emoji/" in m.name and name.endswith("_64.png"):
                dst = os.path.join(EMOJI_DIR, name)
            else:
                continue
            with open(dst, "wb") as f:
                f.write(tf.extractfile(m).read())


def font_path():
    if not os.path.exists(FONT):
        _unpack_kit()
    return FONT


def _candidates(seq):
    cps = [f"{ord(c):x}" for c in seq]
    seen = []
    for c in ("-".join(cps), "-".join(x for x in cps if x != "fe0f"), "-".join(cps + ["fe0f"])):
        if c not in seen:
            seen.append(c)
    return seen


def emoji_path(seq):
    if not os.path.isdir(EMOJI_DIR):
        _unpack_kit()
    cands = _candidates(seq)
    for c in cands:
        p = os.path.join(EMOJI_DIR, c + "_64.png")
        if os.path.exists(p):
            return p
    for c in cands:
        try:
            data = urllib.request.urlopen(EMOJI_CDN.format(c), timeout=30).read()
        except Exception:
            continue
        p = os.path.join(EMOJI_DIR, c + "_64.png")
        with open(p, "wb") as f:
            f.write(data)
        return p
    raise FileNotFoundError(f"no Apple emoji picture for {seq!r} (tried {cands})")
