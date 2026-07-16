"""
Render the Dating Reaction video with the MOVING PiP.

Body = source (full clip) scaled to 1080x1920 with the transparent cutout
reaction overlaid, hopping between the solved corner positions per the motion
segments (hidden segments = no PiP). Then a hard cut to the reaction full-screen
with audio. Audio cross-fades at the seam.

Usage:
  python3 render_dating_reaction.py SOURCE CUTOUT_WEBM REACTION MOTION.json OUT.mp4 \
      [REACTION_TRIM_START] [REACTION_DUR] [HOOK_TEXT] [HOOK_DUR]

HOOK_TEXT is burned on top of the body for the first HOOK_DUR seconds (default
1.8s). Emojis are stripped for the FFmpeg burn (color emoji can't render in
drawtext); the hook is wrapped to fit and shown top-center.
"""
import sys, os, re, json, subprocess, textwrap

SRC, CUTOUT, REACT, MO, OUT = sys.argv[1:6]
RTRIM = float(sys.argv[6]) if len(sys.argv) > 6 else 3.6
RDUR = float(sys.argv[7]) if len(sys.argv) > 7 else 14.7
HOOK = sys.argv[8] if len(sys.argv) > 8 else ""
HOOK_DUR = float(sys.argv[9]) if len(sys.argv) > 9 else 1.8
OW, OH = 1080, 1920


def _find_font():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.environ.get("DR_FONT", ""),
        os.path.join(here, "assets", "TikTokSans36pt-ExtraBold.ttf"),
        os.path.join(here, "TikTokSans36pt-ExtraBold.ttf"),
        os.path.join(here, "..", "fonts", "TikTokSans36pt-ExtraBold.ttf"),
        os.path.join(here, "..", "..", "..", "fonts", "TikTokSans36pt-ExtraBold.ttf"),
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


FONT = _find_font()


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip())


def prep_hook(text):
    """Strip emoji/non-rendering chars, collapse spaces, wrap to lines; write to a
    textfile and return its path (or None if nothing to draw)."""
    if not text or not text.strip():
        return None
    # drop anything above the BMP and common symbol/emoji blocks
    clean = re.sub(r"[\U0001F000-\U0001FAFF←-➿⬀-⯿︀-️‍]", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return None
    lines = textwrap.wrap(clean, width=28)   # no truncation — fit the whole hook
    path = os.path.abspath("_hook_overlay.txt")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path, len(lines)


body_dur = dur(SRC)
segs = [s for s in json.load(open(MO))["segments"] if s["visible"]]

# ---- BODY: base + one scaled+positioned cutout overlay per visible segment ----
inputs = ["-i", SRC]
for _ in segs:
    # explicit libvpx-vp9 decoder so the VP9 alpha channel is preserved
    inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", CUTOUT]

fc = [f"[0:v]scale={OW}:{OH}:force_original_aspect_ratio=increase,"
      f"crop={OW}:{OH},setsar=1,fps=30[base]"]
last = "base"
for i, s in enumerate(segs, start=1):
    w = max(2, int(s["w"] * OW)); h = max(2, int(s["h"] * OH))
    x = int(s["x"] * OW); y = int(s["y"] * OH)
    fc.append(f"[{i}:v]scale={w}:{h},format=yuva420p[p{i}]")
    out = f"v{i}"
    fc.append(f"[{last}][p{i}]overlay={x}:{y}:"
              f"enable='between(t,{s['t0']:.3f},{s['t1']:.3f})'[{out}]")
    last = out

# ---- HOOK: burned top-center for the first HOOK_DUR seconds ----
hook_prep = prep_hook(HOOK)
if hook_prep:
    hook_file, n_lines = hook_prep
    fontsize = {1: 66, 2: 64, 3: 58, 4: 50}.get(n_lines, 44)   # scale to fit
    fc.append(
        f"[{last}]drawtext=textfile='{hook_file}':fontfile='{FONT}':"
        f"fontcolor=white:fontsize={fontsize}:line_spacing=14:"
        f"borderw=7:bordercolor=black:"
        f"shadowcolor=black@0.45:shadowx=0:shadowy=3:"
        f"x=(w-text_w)/2:y=h*0.07:enable='between(t,0,{HOOK_DUR})'[vhook]")
    last = "vhook"

fo = max(0.0, body_dur - 0.45)
fc.append(f"[0:a]afade=t=out:st={fo:.2f}:d=0.45[ba]")

body_cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error"] + inputs + [
    "-filter_complex", ";".join(fc),
    "-map", f"[{last}]", "-map", "[ba]", "-t", f"{body_dur:.2f}",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "body_render.mp4"]
print("rendering body...", subprocess.run(body_cmd, capture_output=True, text=True).stderr[-300:])

# ---- TAIL: reaction full-screen with audio ----
tail_cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{RTRIM}", "-t", f"{RDUR}",
    "-i", REACT, "-filter_complex",
    f"[0:v]scale={OW}:{OH}:force_original_aspect_ratio=increase,crop={OW}:{OH},setsar=1,fps=30[v]",
    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "tail_render.mp4"]
print("rendering tail...", subprocess.run(tail_cmd, capture_output=True, text=True).stderr[-300:])

# ---- CONCAT (hard cut, audio fade-in on tail) ----
cat_cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", "body_render.mp4", "-i", "tail_render.mp4",
    "-filter_complex",
    "[1:a]afade=t=in:st=0:d=0.4[a1];[0:v][0:a][1:v][a1]concat=n=2:v=1:a=1[v][a]",
    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
    "-pix_fmt", "yuv420p", "-c:a", "aac", OUT]
print("concat...", subprocess.run(cat_cmd, capture_output=True, text=True).stderr[-300:])
print("DONE", OUT, "| body", round(body_dur, 2), "s |", len(segs), "visible segments")
