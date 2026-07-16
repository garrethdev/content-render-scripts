#!/usr/bin/env python3
"""Add a rotating music bed to finished conspiracy-kitchen videos (no re-render).

Drop the 3 MP3s in ~/Claude/conspiracy-render/music/, then run this. It identifies
Beach House / Men I Trust / Sade by filename keyword, rotates them across the videos
in sorted order (vid1 Beach House, vid2 Men I Trust, vid3 Sade, repeat), fades in/out,
ducks the volume under the ASMR feel, and writes to 'Edit/with music/' — originals
are left untouched. Video stream is copied (no re-encode), so it's fast.

    python3 ~/Claude/conspiracy-render/add_music.py                 # all BATCH*.mp4
    python3 ~/Claude/conspiracy-render/add_music.py --volume 0.18   # quieter bed
    python3 ~/Claude/conspiracy-render/add_music.py --glob "BATCH4*.mp4"
"""
import os, glob, subprocess, argparse

EDIT = "/Users/garrethdottin/Desktop/AI Video Generation /Character 4 /Edit"
MUSIC = os.path.expanduser("~/Claude/conspiracy-render/music")
OUT = os.path.join(EDIT, "with music")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".flac")
# rotation order; each entry = filename keywords that identify that track
ROTATION = [("beach", "space"), ("men i trust", "show me how", "men_i_trust"), ("sade", "cherish")]

def find_songs():
    files = [f for f in glob.glob(os.path.join(MUSIC, "*")) if f.lower().endswith(AUDIO_EXT)]
    songs = []
    for keys in ROTATION:
        songs.append(next((f for f in files if any(k in os.path.basename(f).lower() for k in keys)), None))
    return songs, files

def dur(path):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return 0.0

def mux(video, song, out, volume=0.22):
    d = dur(video); fo = max(0.5, d - 2.0)
    fc = f"[1:a]afade=t=in:st=0:d=1.5,afade=t=out:st={fo:.2f}:d=2,volume={volume}[a]"
    cmd = ["ffmpeg","-y","-loglevel","error","-i",video,"-stream_loop","-1","-i",song,
           "-filter_complex",fc,"-map","0:v","-map","[a]","-shortest",
           "-c:v","copy","-c:a","aac","-b:a","192k",out]
    subprocess.run(cmd, check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="BATCH*.mp4")
    ap.add_argument("--volume", type=float, default=0.22)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    songs, files = find_songs()
    missing = [ROTATION[i][0] for i, s in enumerate(songs) if not s]
    if missing:
        print("MISSING tracks:", missing)
        print("Files present in music/:", [os.path.basename(f) for f in files] or "(none)")
        print("Drop the 3 MP3s in", MUSIC)
        return
    print("rotation:", [os.path.basename(s) for s in songs])
    vids = sorted(glob.glob(os.path.join(EDIT, a.glob)))
    done = 0
    for i, v in enumerate(vids):
        song = songs[i % len(songs)]
        out = os.path.join(OUT, os.path.basename(v))
        try:
            mux(v, song, out, a.volume); done += 1
            print(f"  [{done}/{len(vids)}] {os.path.basename(v)[:38]} <- {os.path.basename(song)[:22]}")
        except Exception as e:
            print("FAIL", os.path.basename(v), str(e)[:60])
    print(f"DONE: {done}/{len(vids)} -> {OUT}")

if __name__ == "__main__":
    main()
