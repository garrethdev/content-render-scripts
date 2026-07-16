"""
Caption detector — step 1 of the dating-reaction pipeline.

Samples frames across a source clip and reports whether the video ALREADY has
burned-in captions. The downstream pipeline uses this to decide whether to add
its own captions (only when none are present).

Usage:
  python3 caption_detect.py VIDEO [CLIP_IN] [CLIP_OUT] [--transcript "..."] [--json]

Decision logic (in priority order):
  1. TRANSCRIPT MATCH (most reliable): if a transcript is supplied and the OCR'd
     on-screen words overlap it by >= MIN_TRANSCRIPT_MATCHES distinct words, the
     source clearly has burned captions of the spoken line. This handles timed
     captions that are only on screen for part of the clip.
  2. FALLBACK heuristic (no transcript): text appears in >= FRAME_FRACTION of
     sampled frames AND clusters in a consistent vertical band.
"""
import sys
import os
import json
import tempfile
import subprocess
import cv2
import pytesseract
from pytesseract import Output

N_SAMPLES = 16
MIN_CONF = 55
MIN_CHARS = 3
MIN_HEIGHT_FRAC = 0.020   # caption text is >= ~2% of frame height
FRAME_FRACTION = 0.30     # fallback: text in >=30% of frames => captions
BAND_TOL_FRAC = 0.18      # text y-centers must cluster within 18% of height
MIN_TRANSCRIPT_MATCHES = 2  # distinct OCR words matching transcript => captions

import re
_STOP = {"the", "and", "you", "that", "was", "for", "are", "but", "with",
         "this", "have", "all", "your", "its"}


def _words(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
            if w not in _STOP}


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def sample_times(t0, t1, n):
    if t1 <= t0:
        t1 = t0 + 1.0
    step = (t1 - t0) / (n + 1)
    return [t0 + step * (i + 1) for i in range(n)]


def frame_text_boxes(img):
    """Return list of (y_center_frac, text) for caption-like words in a frame."""
    h = img.shape[0]
    min_h = MIN_HEIGHT_FRAC * h
    data = pytesseract.image_to_data(img, output_type=Output.DICT, config="--psm 11")
    boxes = []
    for i in range(len(data["text"])):
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        txt = data["text"][i].strip()
        if conf < MIN_CONF or len(txt) < MIN_CHARS:
            continue
        if sum(c.isalpha() for c in txt) < len(txt) * 0.6:
            continue
        bh = data["height"][i]
        if bh < min_h:
            continue
        yc = (data["top"][i] + bh / 2) / h
        boxes.append((yc, txt))
    return boxes


def detect(video, clip_in=None, clip_out=None, transcript=None):
    dur = ffprobe_duration(video)
    t0 = 0.0 if clip_in is None else float(clip_in)
    t1 = dur if clip_out is None else float(clip_out)
    times = sample_times(t0, t1, N_SAMPLES)

    frames_with_text = 0
    all_yc = []
    ocr_words = set()
    sample_words = []
    tmp = tempfile.mkdtemp()
    for k, t in enumerate(times):
        fp = os.path.join(tmp, f"f{k:02d}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
                        "-frames:v", "1", fp], capture_output=True)
        img = cv2.imread(fp)
        if img is None:
            continue
        boxes = frame_text_boxes(img)
        if boxes:
            frames_with_text += 1
            all_yc.extend(b[0] for b in boxes)
            sample_words.extend(b[1] for b in boxes[:4])
            for _, txt in boxes:
                ocr_words |= _words(txt)

    n = len(times)
    frac = frames_with_text / n if n else 0.0
    banded = False
    if all_yc:
        all_yc.sort()
        mid = all_yc[len(all_yc) // 2]
        within = sum(1 for y in all_yc if abs(y - mid) <= BAND_TOL_FRAC)
        banded = within >= 0.6 * len(all_yc)

    # Primary signal: OCR words matching the spoken transcript.
    matches = sorted(ocr_words & _words(transcript)) if transcript else []
    by_transcript = len(matches) >= MIN_TRANSCRIPT_MATCHES
    by_fallback = frac >= FRAME_FRACTION and banded
    has_captions = by_transcript or by_fallback

    return {
        "video": os.path.basename(video),
        "clip_in": t0, "clip_out": t1,
        "frames_sampled": n,
        "frames_with_text": frames_with_text,
        "fraction_with_text": round(frac, 2),
        "text_banded": banded,
        "transcript_matches": matches,
        "matched_by": "transcript" if by_transcript else ("fallback" if by_fallback else "none"),
        "has_captions": has_captions,
        "decision": "SKIP captions (source already has them)" if has_captions
                    else "ADD captions (source has none)",
        "sample_words": sample_words[:10],
    }


if __name__ == "__main__":
    transcript = None
    if "--transcript" in sys.argv:
        ti = sys.argv.index("--transcript")
        transcript = sys.argv[ti + 1]
        del sys.argv[ti:ti + 2]
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv
    video = args[0]
    ci = args[1] if len(args) > 1 else None
    co = args[2] if len(args) > 2 else None
    res = detect(video, ci, co, transcript)
    if as_json:
        print(json.dumps(res))
    else:
        for k, v in res.items():
            print(f"{k:20}: {v}")
