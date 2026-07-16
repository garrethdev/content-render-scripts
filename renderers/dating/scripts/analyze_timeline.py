"""
Time-resolved analyzer + face tracking.

Samples a clip at a steady cadence, detects gated faces and caption text per
frame (via face_lib), then LINKS face detections across frames into tracks.
Tracks give: (a) a temporal false-positive filter — a real face forms a track
spanning many frames; a one-off detection forms a 1-frame track and is dropped;
and (b) smooth per-time face trajectories (gaps interpolated) that drive PiP
motion downstream.

Output JSON (coords normalized 0..1 of frame, resolution-independent):
  { fps, duration, frame_w, frame_h,
    frames: [ {t, faces:[[x,y,w,h,score]], text:[[x,y,w,h]]} ],
    face_tracks: [ {id, frames:[i...], points:[{t,x,y,w,h}]} ] }

Usage:
  python3 analyze_timeline.py CLIP OUT.json [ANALYZE_FPS]
"""
import sys, json
import cv2
import face_lib as fl

CLIP = sys.argv[1]
OUT = sys.argv[2]
FPS = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0

IOU_MATCH = 0.3       # link a detection to a track if IoU exceeds this
CENTROID_FRAC = 0.12  # ...or if centroid within this fraction of frame diagonal
MAX_GAP = 3           # close a track after this many missed sampled frames


def iou(a, b):
    ax, ay, aw, ah = a[:4]; bx, by, bw, bh = b[:4]
    x1 = max(ax, bx); y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw); y2 = min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    u = aw * ah + bw * bh - inter
    return inter / u if u > 0 else 0.0


def centroid(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def main():
    cap = cv2.VideoCapture(CLIP)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, int(round(src_fps / FPS)))
    diag = (W ** 2 + H ** 2) ** 0.5
    det = fl.load_detector()

    frames = []          # per sampled frame: {t, faces(px), text(px)}
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step != 0:
            i += 1
            continue
        t = i / src_fps
        faces = fl.detect_faces(det, fr)            # [(x,y,w,h,score)]
        text = fl.detect_text(fr)                   # [(x,y,w,h)]
        frames.append({"t": round(t, 3), "faces": faces, "text": text})
        i += 1
    cap.release()

    # ---- link faces into tracks (greedy IoU / centroid, across sampled frames) ----
    tracks = []  # each: {points:[(fidx, box)], last_fidx}
    for fidx, fr in enumerate(frames):
        used = set()
        # try to extend existing open tracks
        for tr in tracks:
            if fidx - tr["last_fidx"] > MAX_GAP:
                continue
            best, bj = 0.0, -1
            lb = tr["points"][-1][1]
            for j, fb in enumerate(fr["faces"]):
                if j in used:
                    continue
                score = iou(lb, fb)
                if score < IOU_MATCH:
                    cx0, cy0 = centroid(lb); cx1, cy1 = centroid(fb)
                    d = ((cx0 - cx1) ** 2 + (cy0 - cy1) ** 2) ** 0.5
                    score = max(score, 1 - d / (CENTROID_FRAC * diag)) if d < CENTROID_FRAC * diag else 0
                if score > best:
                    best, bj = score, j
            if bj >= 0:
                tr["points"].append((fidx, fr["faces"][bj]))
                tr["last_fidx"] = fidx
                used.add(bj)
        # unmatched detections start new tracks
        for j, fb in enumerate(fr["faces"]):
            if j not in used:
                tracks.append({"points": [(fidx, fb)], "last_fidx": fidx})

    n = len(frames)
    min_len = max(2, round(0.15 * n))
    min_span_s = 0.5
    kept = []
    for tr in tracks:
        pts = tr["points"]
        span_s = (pts[-1][0] - pts[0][0]) / FPS
        if len(pts) >= min_len and span_s >= min_span_s:
            kept.append(tr)

    # interpolate gaps within each kept track, normalize, attach timeline
    face_tracks = []
    for tid, tr in enumerate(kept):
        pts = tr["points"]
        bym = {fidx: box for fidx, box in pts}
        f0, f1 = pts[0][0], pts[-1][0]
        out_pts = []
        for fidx in range(f0, f1 + 1):
            if fidx in bym:
                box = bym[fidx]
            else:  # linear interp between nearest known neighbors
                prev = max(k for k in bym if k < fidx)
                nxt = min(k for k in bym if k > fidx)
                a, b = bym[prev], bym[nxt]
                r = (fidx - prev) / (nxt - prev)
                box = tuple(a[k] + (b[k] - a[k]) * r for k in range(4))
            out_pts.append({
                "t": round(frames[fidx]["t"], 3),
                "x": round(box[0] / W, 4), "y": round(box[1] / H, 4),
                "w": round(box[2] / W, 4), "h": round(box[3] / H, 4),
            })
        face_tracks.append({"id": tid, "frames": [f0, f1], "n": len(pts), "points": out_pts})

    # normalize per-frame boxes for output
    def norm_boxes(bs, scored):
        out = []
        for b in bs:
            row = [round(b[0] / W, 4), round(b[1] / H, 4), round(b[2] / W, 4), round(b[3] / H, 4)]
            if scored:
                row.append(round(b[4], 3))
            out.append(row)
        return out

    out = {
        "fps": FPS, "duration": round(n / FPS, 2), "frame_w": W, "frame_h": H,
        "n_frames": n,
        "frames": [{"t": f["t"], "faces": norm_boxes(f["faces"], True),
                    "text": norm_boxes(f["text"], False)} for f in frames],
        "face_tracks": face_tracks,
    }
    json.dump(out, open(OUT, "w"))
    print(f"{CLIP}: {n} frames @ {FPS}fps | raw tracks {len(tracks)} -> kept {len(kept)} "
          f"(min_len={min_len}) | track lengths {[len(t['points']) for t in kept]}")


if __name__ == "__main__":
    main()
