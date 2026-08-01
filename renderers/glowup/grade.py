#!/usr/bin/env python3
"""Apply the maxxingnation grade to source photos so recycled images read as one brand.

Recipe from maxxingnation-research/STYLE_SPEC.md section 1:
  eq=saturation=0.6:contrast=1.12:brightness=-0.06, colorbalance=sm=.08:mm=.04, vignette=PI/5

NOTE: the spec's `colorbalance=sm=.08:mm=.04` is not valid ffmpeg — colorbalance has no
`sm`/`mm` options, only per-channel rs/gs/bs (shadows), rm/gm/bm (midtones), rh/gh/bh
(highlights). Translated below to the spec's stated INTENT: "warm split-tone in shadows
(~25 deg hue)" — push red up and blue down in shadows and midtones.
Canvas 1080x1440 (3:4), centre-cropped to fill — spec section 2.

Usage: python3 grade.py out_dir img1 [img2 ...]
"""
import os, subprocess, sys

W, H = 1080, 1440
CROP = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
WARM = "colorbalance=rs=.08:gs=.03:bs=-.05:rm=.04:gm=.01:bm=-.03"

# default: the spec's numbers
VF = f"{CROP},eq=saturation=0.6:contrast=1.12:brightness=-0.06,{WARM},vignette=PI/5"

# strong: matches the maxxingnation reference more closely — crushed blacks, low
# saturation, heavy vignette. curves pulls the shadow end down so backgrounds go
# near-black instead of grey, which is the single biggest tell of their look.
VF_STRONG = (f"{CROP},"
             "curves=all='0/0 0.25/0.10 0.6/0.55 1/0.97',"
             "eq=saturation=0.42:contrast=1.28:brightness=-0.10,"
             f"{WARM},vignette=PI/3.5")


def grade(src, dst, strong=False):
    subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf",
                    VF_STRONG if strong else VF, "-q:v", "2", dst, "-y"], check=True)
    return dst


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--strong"]
    strong = "--strong" in sys.argv[1:]
    out = args[0]
    os.makedirs(out, exist_ok=True)
    for src in args[1:]:
        suffix = "_strong.jpg" if strong else "_graded.jpg"
        name = os.path.splitext(os.path.basename(src))[0] + suffix
        print(grade(src, os.path.join(out, name), strong))
