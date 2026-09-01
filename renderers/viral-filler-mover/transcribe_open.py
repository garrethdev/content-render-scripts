#!/usr/bin/env python3
"""Transcribe an audio file -> JSON list of spoken words (lowercased, len>=3).
Run by the .audio-venv python (has faster_whisper). Usage: transcribe_open.py WAV
"""
import sys, json, re
from faster_whisper import WhisperModel

def main():
    wav = sys.argv[1]
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(wav, language="en")
    words = set()
    for s in segs:
        for w in re.findall(r"[a-z']+", s.text.lower()):
            if len(w) >= 3:
                words.add(w)
    print(json.dumps(sorted(words)))

if __name__ == "__main__":
    main()
