#!/usr/bin/env python3
"""
Analyze a base filler clip ONCE and write a reusable manifest.

Each base video is rendered 3x (3 hooks x 3 PiP characters), so the expensive
vision work — face detection (cv2 YuNet) + burned-caption OCR (Tesseract) —
must run only once. This script does that and caches everything the renderer
needs into a JSON manifest:

  { base, duration, fps,
    face:          {top, bottom, cx, cy, present_frac},   # normalized 0..1
    caption_bands: [[y0,y1], ...],                          # existing on-screen text to avoid
    pip:           {pip_w_frac, pip_h_frac, hook_dur, segments:[...]} }  # subject-aware motion

The face box lets the renderer keep the text hook OFF the face; the motion
segments (from motion_solver, which avoids face + captions) place the PiP.
Both are BASE-only, so all 3 renders reuse this file — zero re-analysis.

Usage:
  python3 probe_base.py BASE.mp4 OUT.manifest.json [PIP_H_FRAC] [HOOK_DUR]

Relies on the proven dating-reaction analyzer/solver (DR_DIR, has cv2+tesseract
in its venv). Cheap + local: no API calls.
"""
import os, sys, json, subprocess, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DR = os.environ.get("DR_DIR", os.path.expanduser("~/Claude/dating-reaction"))
PY = os.path.join(DR, ".venv", "bin", "python")
ANALYZE = os.path.join(DR, "scripts", "analyze_timeline.py")
SOLVER = os.path.join(DR, "scripts", "motion_solver.py")
CUTOUT_ASPECT = 458 / 608                      # char cutout w/h (matches assets)
OW, OH = 1080, 1920


def _pct(xs, p):
    if not xs:
        return 0.0
    xs = sorted(xs); k = max(0, min(len(xs) - 1, int(p / 100.0 * (len(xs) - 1))))
    return xs[k]


def face_aggregate(frames):
    tops, bots, cxs, cys = [], [], [], []
    seen = 0
    for f in frames:
        fc = f.get("faces") or []
        if fc:
            seen += 1
            # largest face in the frame
            x, y, w, h = max(fc, key=lambda b: b[2] * b[3])[:4]
            tops.append(y); bots.append(y + h); cxs.append(x + w / 2); cys.append(y + h / 2)
    if not tops:
        return {"top": 0.18, "bottom": 0.55, "cx": 0.5, "cy": 0.36, "present_frac": 0.0}
    return {"top": round(_pct(tops, 20), 4), "bottom": round(_pct(bots, 80), 4),
            "cx": round(statistics.median(cxs), 4), "cy": round(statistics.median(cys), 4),
            "present_frac": round(seen / max(1, len(frames)), 3)}


def caption_bands(frames, min_frames=2):
    """Vertical y-bands where burned text (OCR) recurs -> the renderer avoids them."""
    GH = 160
    rows = [0] * GH
    for f in frames:
        hit = set()
        for b in (f.get("text") or []):
            y0 = int((b[1] - 0.01) * GH); y1 = int((b[1] + b[3] + 0.01) * GH)
            for r in range(max(0, y0), min(GH, y1)):
                hit.add(r)
        for r in hit:
            rows[r] += 1
    bands, run = [], None
    for r in range(GH):
        if rows[r] >= min_frames:
            run = [r, r] if run is None else [run[0], r]
        elif run is not None:
            bands.append(run); run = None
    if run is not None:
        bands.append(run)
    return [[round(a / GH, 3), round((b + 1) / GH, 3)] for a, b in bands]


def main():
    base = sys.argv[1]; out = sys.argv[2]
    pip_h_frac = float(sys.argv[3]) if len(sys.argv) > 3 else 0.24
    hook_dur = float(sys.argv[4]) if len(sys.argv) > 4 else 2.6

    pip_w_frac = round(pip_h_frac * (OH / OW) * CUTOUT_ASPECT, 4)   # px-consistent footprint
    tl = out + ".tl.json"; mo = out + ".motion.json"

    subprocess.run([PY, ANALYZE, base, tl, "4"], check=True)
    subprocess.run([PY, SOLVER, tl, mo,
                    f"{pip_w_frac}", f"{pip_h_frac}", "0.03", "0.55",
                    f"{hook_dur}", "0.18"], check=True)

    tld = json.load(open(tl)); frames = tld["frames"]
    motion = json.load(open(mo))
    manifest = {
        "base": os.path.abspath(base),
        "duration": tld["duration"], "fps": tld["fps"],
        "face": face_aggregate(frames),
        "caption_bands": caption_bands(frames),
        "pip": {"pip_w_frac": pip_w_frac, "pip_h_frac": pip_h_frac,
                "hook_dur": hook_dur, "segments": motion["segments"]},
    }
    json.dump(manifest, open(out, "w"), indent=2)
    for tmp in (tl, mo):
        try: os.remove(tmp)
        except OSError: pass
    fa = manifest["face"]
    print(f"[probe] {os.path.basename(base)} -> {out}")
    print(f"  face top={fa['top']} bottom={fa['bottom']} present={fa['present_frac']} | "
          f"caption_bands={manifest['caption_bands']} | pip segments={len(motion['segments'])}")


if __name__ == "__main__":
    main()
