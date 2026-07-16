"""
Make the transparent cutout reaction clip.

Takes the reaction video and the time range of the SILENT reaction (the part
used as the corner PiP), removes the background per-frame (rembg
u2net_human_seg), scales to a target height, and writes a VP9 webm WITH ALPHA
that the renderer overlays.

Usage:
  python3 make_cutout.py REACTION OUT.webm [START] [END] [TARGET_H] [FPS]

Defaults: START=0, END=3.6, TARGET_H=608, FPS=12.
Requires: rembg, onnxruntime, ffmpeg.  (pip install rembg onnxruntime --break-system-packages)
"""
import sys, os, glob, tempfile, subprocess
import cv2
from rembg import remove, new_session

REACT = sys.argv[1]
OUT = sys.argv[2]
START = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
END = float(sys.argv[4]) if len(sys.argv) > 4 else 3.6
TARGET_H = int(sys.argv[5]) if len(sys.argv) > 5 else 608
FPS = int(sys.argv[6]) if len(sys.argv) > 6 else 12

tmp = tempfile.mkdtemp()
subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(START),
                "-t", str(END - START), "-i", REACT, "-vf", f"fps={FPS}",
                os.path.join(tmp, "raw_%03d.png")], check=True)

sess = new_session("u2net_human_seg")
cut_dir = os.path.join(tmp, "cut"); os.makedirs(cut_dir, exist_ok=True)
for fp in sorted(glob.glob(os.path.join(tmp, "raw_*.png"))):
    co = remove(cv2.imread(fp), session=sess)        # BGRA, bg removed
    sc = TARGET_H / co.shape[0]
    co = cv2.resize(co, (int(round(co.shape[1] * sc)), TARGET_H), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(cut_dir, os.path.basename(fp)), co)

# VP9 with alpha (yuva420p). NOTE downstream: decode with -c:v libvpx-vp9 to keep alpha.
subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", str(FPS),
                "-i", os.path.join(cut_dir, "raw_%03d.png"),
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "1M",
                "-auto-alt-ref", "0", OUT], check=True)
print("wrote", OUT)
