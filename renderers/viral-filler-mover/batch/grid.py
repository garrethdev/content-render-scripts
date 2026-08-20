#!/usr/bin/env python3
"""Contact sheet for the batch (standing rule: every batch report ships a random visual grid).
Pulls the hook-window frame from N randomly sampled renders into one PNG grid.
  python3 grid.py [N] [out.png]
"""
import os, sys, glob, random, subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FF = "/opt/homebrew/bin/ffmpeg"
TMP = os.path.join(HERE, "qa_frames"); os.makedirs(TMP, exist_ok=True)
COLS, CW = 6, 300
FONT = os.path.join(os.path.dirname(HERE), "assets", "hook-font.ttf")

n   = int(sys.argv[1]) if len(sys.argv) > 1 else 24
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "grid.png")

vids = sorted(glob.glob(os.path.join(HERE, "renders", "*.mp4")))
random.Random(7).shuffle(vids); vids = sorted(vids[:n])

tiles = []
for v in vids:
    stem = os.path.splitext(os.path.basename(v))[0]
    p = os.path.join(TMP, f"{stem}_hook.jpg")
    if not os.path.exists(p):
        subprocess.run([FF,"-y","-loglevel","error","-ss","1.2","-i",v,"-frames:v","1",
                        "-vf","scale=540:-2","-q:v","4",p], check=True)
    tiles.append((p, stem))

CH = int(CW * 1920 / 1080)
rows = (len(tiles) + COLS - 1) // COLS
LBL = 26
sheet = Image.new("RGB", (COLS*CW, rows*(CH+LBL)), (17,17,19))
d = ImageDraw.Draw(sheet)
try: f = ImageFont.truetype(FONT, 15)
except Exception: f = ImageFont.load_default()

for i,(p,stem) in enumerate(tiles):
    x, y = (i % COLS)*CW, (i // COLS)*(CH+LBL)
    sheet.paste(Image.open(p).resize((CW,CH)), (x,y))
    parts = stem.split("_")
    d.text((x+5, y+CH+5), f"{parts[1]} {parts[-1]}", fill=(215,215,220), font=f)
sheet.save(out)
print(f"grid: {len(tiles)} tiles -> {out}  ({sheet.size[0]}x{sheet.size[1]})")
