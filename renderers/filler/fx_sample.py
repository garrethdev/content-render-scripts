#!/usr/bin/env python3
"""Sample: jitter + punch applied to VIDEO ONLY, then text overlaid on top (so the
cut-in does not zoom/clip the caption). Demonstrates the corrected render order for render_ba.py."""
import os, subprocess
import render_ba as R

CID = "GBA-001"
BEFORE = "Before_grandma_character_4_7-AfterEffects.mp4"
TEXT = "I kept waiting until I earned the good life."

bkey = BEFORE if BEFORE.startswith("before/") else "before/" + BEFORE
src = os.path.join(R.WORK, CID + "_b_src.mp4")
if not os.path.exists(src):
    R.download(R.sign_url(R.SRC_BUCKET, bkey), src)

sm = os.path.join(R.WORK, "fx_samples"); os.makedirs(sm, exist_ok=True)
png = os.path.join(sm, CID + "_th.png")
R.build_text_png(TEXT, png)   # 1080x1920 transparent, text ~75% down, fixed size

JX = "if(lt(t,1.5),(4*sin(2*PI*1.1*t)+1.5*sin(2*PI*3.0*t))*(1-t/1.5),0)"
JY = "if(lt(t,1.5),(3.5*sin(2*PI*1.4*t)+1.2*sin(2*PI*3.7*t))*(1-t/1.5),0)"
fc = (
    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,"
    "scale=1144:2036,crop=w=1080:h=1920:x='32+(" + JX + ")':y='58+(" + JY + ")',setsar=1,split=2[base][z];"
    "[z]crop=w=864:h=1536:x=(iw-864)/2:y=(ih-1536)/2,scale=1080:1920,setsar=1[zoom];"
    "[base][zoom]overlay=x=0:y=0:enable='between(t,1.5,8)'[fx];"
    "[fx][1:v]overlay=0:0[out]"
)
out = os.path.join(sm, "v6_textfixed.mp4")
subprocess.run([R.FF, "-y", "-loglevel", "error", "-t", "7", "-i", src, "-i", png,
                "-filter_complex", fc, "-map", "[out]", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-pix_fmt", "yuv420p", "-an", out], check=True, timeout=300)
print("OK", out, os.path.getsize(out))
