#!/usr/bin/env python3
"""OCR helper — run by the dating-reaction venv (has cv2 + pytesseract).
Reads image paths from argv, prints JSON: [{path, words:[{t,h,y,conf}]}]. Words are lowercased,
h/y normalized to frame height. Kept minimal so the main worker can call it as a subprocess.
"""
import sys, json
import cv2, pytesseract
from pytesseract import Output

def words_in(path):
    img = cv2.imread(path)
    if img is None:
        return []
    H = img.shape[0]
    data = pytesseract.image_to_data(img, output_type=Output.DICT, config="--psm 11")
    out = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip().lower()
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if conf < 50 or len(t) < 3:
            continue
        if sum(c.isalpha() for c in t) < len(t) * 0.6:
            continue
        out.append({"t": t, "h": data["height"][i] / H, "y": data["top"][i] / H, "conf": conf})
    return out

if __name__ == "__main__":
    print(json.dumps([{"path": p, "words": words_in(p)} for p in sys.argv[1:]]))
