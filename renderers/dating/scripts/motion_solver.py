"""
Per-segment PiP motion solver.

Consumes the timeline (face tracks + per-frame text) from analyze_timeline.py
and produces a time-varying PiP placement: the PiP HOLDS a spot until the
face/captions intrude on it (hysteresis -> no jitter), then RELOCATES to the
best clean spot, shrinking to fit if needed, and HIDES when no clean spot
exists. Output is a list of segments the renderer animates between.

Coordinates are normalized 0..1. Source clips are ~9:16 like the 1080x1920
output, so normalized source coords map directly to the output canvas.

Output JSON:
  { pip_aspect, segments: [ {t0, t1, visible, x, y, w, h} ] }   (x,y = top-left)

Usage:
  python3 motion_solver.py TIMELINE.json OUT.json \
      [PIP_W_FRAC] [PIP_H_FRAC] [MARGIN_FRAC] [MIN_SCALE]
"""
import sys, json

TL = sys.argv[1]
OUT = sys.argv[2]
PIP_W = float(sys.argv[3]) if len(sys.argv) > 3 else 0.424   # cutout 458/1080
PIP_H = float(sys.argv[4]) if len(sys.argv) > 4 else 0.317   # cutout 608/1920
MARGIN = float(sys.argv[5]) if len(sys.argv) > 5 else 0.025
MIN_SCALE = float(sys.argv[6]) if len(sys.argv) > 6 else 0.5
# Hook overlay occupies a top band for its first HOOK_DUR seconds; the PiP must
# avoid it while it is on screen (time-scoped, NOT clip-wide).
HOOK_DUR = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
HOOK_BAND = float(sys.argv[8]) if len(sys.argv) > 8 else 0.20

GW, GH = 96, 160          # coarse occupancy grid
FACE_W = 6.0              # face pixel weight vs text
FACE_PAD = 0.25           # pad face box by 25% of its width
# OCR only catches a thin sliver of a multi-line caption, so pad text boxes
# generously (esp. vertically) to cover the whole caption block. Text is a HARD
# avoid (no overlap allowed), same as faces.
TEXT_PAD_X = 0.03
TEXT_PAD_Y = 0.06


def build_grid(frame):
    """Rasterize avoid-cost onto GW x GH from a frame's faces + text."""
    g = [[0.0] * GW for _ in range(GH)]

    def fill(x, y, w, h, val):
        x0 = max(0, int(x * GW)); y0 = max(0, int(y * GH))
        x1 = min(GW, int((x + w) * GW)); y1 = min(GH, int((y + h) * GH))
        for yy in range(y0, y1):
            row = g[yy]
            for xx in range(x0, x1):
                row[xx] = max(row[xx], val)

    for b in frame["faces"]:
        x, y, w, h = b[:4]
        px = FACE_PAD * w
        fill(x - px, y - px, w + 2 * px, h + 2 * px, FACE_W)
    for b in frame["text"]:
        x, y, w, h = b[:4]
        fill(x - TEXT_PAD, y - TEXT_PAD, w + 2 * TEXT_PAD, h + 2 * TEXT_PAD,
             max(1.0, _cell(g, x, y)))  # text weight 1 (don't lower a face cell)
    return g


def _cell(g, x, y):
    return g[min(GH - 1, max(0, int(y * GH)))][min(GW - 1, max(0, int(x * GW)))]


def integral(g):
    I = [[0.0] * (GW + 1) for _ in range(GH + 1)]
    for y in range(GH):
        for x in range(GW):
            I[y + 1][x + 1] = g[y][x] + I[y][x + 1] + I[y + 1][x] - I[y][x]
    return I


def wsum(I, x0, y0, w, h):
    x1, y1 = x0 + w, y0 + h
    return I[y1][x1] - I[y0][x1] - I[y1][x0] + I[y0][x0]


def face_only_grid(frame):
    g = [[0.0] * GW for _ in range(GH)]
    for b in frame["faces"]:
        x, y, w, h = b[:4]; px = FACE_PAD * w
        x0 = max(0, int((x - px) * GW)); y0 = max(0, int((y - px) * GH))
        x1 = min(GW, int((x + w + px) * GW)); y1 = min(GH, int((y + h + px) * GH))
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                g[yy][xx] = 1.0
    return g


CORNERS_FRAC = [(MARGIN, MARGIN), (1 - MARGIN, MARGIN),
                (MARGIN, 1 - MARGIN), (1 - MARGIN, 1 - MARGIN)]


def solve_frame(frame, prefer=None):
    """Best placement for a frame. Shrink-to-fit. Returns (x,y,w,h) top-left
    normalized, or None if nothing clean even at min scale. `prefer` biases
    toward an existing position (for stability)."""
    Icost = integral(build_grid(frame))
    Iface = integral(face_only_grid(frame))
    best_any = None
    for i in range(int((1 - MIN_SCALE) / 0.1) + 1):
        s = 1.0 - 0.1 * i
        pw = PIP_W * s; ph = PIP_H * s
        gw = max(1, int(pw * GW)); gh = max(1, int(ph * GH))
        cand = []
        # candidate top-left positions: 4 corners + coarse grid
        xs = sorted(set([int(MARGIN * GW), GW - gw - int(MARGIN * GW)] +
                        list(range(int(MARGIN * GW), GW - gw - int(MARGIN * GW) + 1, 6))))
        ys = sorted(set([int(MARGIN * GH), GH - gh - int(MARGIN * GH)] +
                        list(range(int(MARGIN * GH), GH - gh - int(MARGIN * GH) + 1, 6))))
        for gy in ys:
            if gy < 0 or gy + gh > GH:
                continue
            for gx in xs:
                if gx < 0 or gx + gw > GW:
                    continue
                f = wsum(Iface, gx, gy, gw, gh)
                c = wsum(Icost, gx, gy, gw, gh)
                # corner distance (grid)
                cd = min((gx - cx * GW) ** 2 + (gy - cy * GH) ** 2 for cx, cy in CORNERS_FRAC)
                # stability bias: prefer staying near previous placement
                sb = 0
                if prefer is not None:
                    px = prefer[0] * GW; py = prefer[1] * GH
                    sb = (gx - px) ** 2 + (gy - py) ** 2
                cand.append((f, c, sb, cd, gx, gy, gw, gh, s))
        cand.sort()
        f, c, *_ , gx, gy, gw2, gh2, s2 = cand[0]
        if best_any is None:
            best_any = cand[0]
        area = gw2 * gh2
        if f == 0 and c < ACCEPT_TEXT * area * FACE_W:  # clean at this size
            return (gx / GW, gy / GH, gw2 / GW, gh2 / GH), True
    # nothing fully clean: return least-overlap (face-min) as a soft fallback
    f, c, *_ , gx, gy, gw2, gh2, s2 = best_any
    return (gx / GW, gy / GH, gw2 / GW, gh2 / GH), (f == 0)


def or_boxes(face_g, cost_g, frame):
    """OR a frame's faces/text into running union grids (in place)."""
    for b in frame["faces"]:
        x, y, w, h = b[:4]; px = FACE_PAD * w
        x0 = max(0, int((x - px) * GW)); y0 = max(0, int((y - px) * GH))
        x1 = min(GW, int((x + w + px) * GW)); y1 = min(GH, int((y + h + px) * GH))
        for yy in range(y0, y1):
            fr_, cr_ = face_g[yy], cost_g[yy]
            for xx in range(x0, x1):
                fr_[xx] = 1.0; cr_[xx] = FACE_W
    # Captions are horizontal bands and OCR only catches part of a line, so
    # block the ENTIRE width at the caption's y-band (with vertical padding).
    for b in frame["text"]:
        x, y, w, h = b[:4]
        y0 = max(0, int((y - TEXT_PAD_Y) * GH))
        y1 = min(GH, int((y + h + TEXT_PAD_Y) * GH))
        for yy in range(y0, y1):
            cr_ = cost_g[yy]
            for xx in range(GW):
                if cr_[xx] < 1.0:
                    cr_[xx] = 1.0


def _face_centroid(face_g):
    sx = sy = ncnt = 0
    for y in range(GH):
        row = face_g[y]
        for x in range(GW):
            if row[x] > 0:
                sx += x; sy += y; ncnt += 1
    if ncnt == 0:
        return GW * 0.5, GH * 0.5
    return sx / ncnt, sy / ncnt


def search_clean(face_g, cost_g):
    """Find the PiP placement, CORNER-FIRST. Prefer the largest clean corner
    (no face/text overlap), choosing the corner farthest from the face so the
    PiP sits opposite the subject. Only if no corner is clean at any size do we
    fall back to a free-form position. Returns (x,y,w,h) top-left or None."""
    Iface = integral(face_g); Icost = integral(cost_g)
    fcx, fcy = _face_centroid(face_g)

    def clean(gx, gy, gw, gh):
        if gx < 0 or gy < 0 or gx + gw > GW or gy + gh > GH:
            return False
        return wsum(Iface, gx, gy, gw, gh) == 0 and wsum(Icost, gx, gy, gw, gh) == 0

    m = int(MARGIN * GW); mh = int(MARGIN * GH)
    for i in range(int((1 - MIN_SCALE) / 0.1) + 1):
        s = 1.0 - 0.1 * i
        gw = max(1, int(PIP_W * s * GW)); gh = max(1, int(PIP_H * s * GH))
        corners = [
            (m, mh), (GW - gw - m, mh),                 # top-left, top-right
            (m, GH - gh - mh), (GW - gw - m, GH - gh - mh),  # bottom-left, bottom-right
        ]
        clean_corners = [(gx, gy) for (gx, gy) in corners if clean(gx, gy, gw, gh)]
        if clean_corners:
            # farthest corner from the face centroid (PiP opposite the subject)
            gx, gy = max(clean_corners,
                         key=lambda c: (c[0] + gw / 2 - fcx) ** 2 + (c[1] + gh / 2 - fcy) ** 2)
            return (gx / GW, gy / GH, gw / GW, gh / GH)

    # ---- fallback: no clean corner at any size -> free-form sliding search ----
    for i in range(int((1 - MIN_SCALE) / 0.1) + 1):
        s = 1.0 - 0.1 * i
        gw = max(1, int(PIP_W * s * GW)); gh = max(1, int(PIP_H * s * GH))
        xs = list(range(m, GW - gw - m + 1, 4))
        ys = list(range(mh, GH - gh - mh + 1, 4))
        best = None
        for gy in ys:
            for gx in xs:
                if wsum(Iface, gx, gy, gw, gh) or wsum(Icost, gx, gy, gw, gh):
                    continue
                cd = min((gx - cx * GW) ** 2 + (gy - cy * GH) ** 2 for cx, cy in CORNERS_FRAC)
                if best is None or cd < best[0]:
                    best = (cd, gx, gy, gw, gh)
        if best:
            _, gx, gy, gw, gh = best
            return (gx / GW, gy / GH, gw / GW, gh / GH)
    return None


def corner_placements(face_g, cost_g):
    """For each of the 4 corners, the largest size at which it is clean (no
    face/text overlap). Returns {corner_id: (x,y,w,h)} (top-left normalized)."""
    Iface = integral(face_g); Icost = integral(cost_g)
    m = int(MARGIN * GW); mh = int(MARGIN * GH)
    res = {}
    for i in range(int((1 - MIN_SCALE) / 0.1) + 1):
        s = 1.0 - 0.1 * i
        gw = max(1, int(PIP_W * s * GW)); gh = max(1, int(PIP_H * s * GH))
        defs = {0: (m, mh), 1: (GW - gw - m, mh),
                2: (m, GH - gh - mh), 3: (GW - gw - m, GH - gh - mh)}
        for cid, (gx, gy) in defs.items():
            if cid in res:
                continue
            if gx < 0 or gy < 0 or gx + gw > GW or gy + gh > GH:
                continue
            if wsum(Iface, gx, gy, gw, gh) == 0 and wsum(Icost, gx, gy, gw, gh) == 0:
                res[cid] = (gx / GW, gy / GH, gw / GW, gh / GH)
        if len(res) == 4:
            break
    return res


def main():
    d = json.load(open(TL))
    frames = d["frames"]
    n = len(frames)
    dt = 1.0 / d["fps"]
    D = n * dt

    # STABILITY-FIRST (user feedback 2026-07-11: hopping reads as chaotic).
    # Prefer ONE static placement for the whole clip; only fall back to
    # intervals (moves) when no corner stays clean for the full duration.
    # Interval mode itself now prefers STAYING in the same corner.
    nseg = max(2, min(5, round(D / 2.5) + 1))
    bounds = [round(k * n / nseg) for k in range(nseg + 1)]

    # CLIP-WIDE caption band: OCR catches captions inconsistently frame to frame
    # (and misses some shots entirely), but captions hold a steady vertical band.
    # So count how many frames put text on each grid row, keep rows seen in >=2
    # frames, pad them, and block that full-width band for the WHOLE clip. This
    # protects captions even in frames/shots where OCR missed them.
    rowcount = [0] * GH
    for f in frames:
        hit = set()
        for b in f["text"]:
            y0 = int((b[1] - 0.01) * GH); y1 = int((b[1] + b[3] + 0.01) * GH)
            for r in range(max(0, y0), min(GH, y1)):
                hit.add(r)
        for r in hit:
            rowcount[r] += 1
    band = set()
    padU = int(0.04 * GH); padD = int(0.07 * GH)   # pad up a little, down more (2nd line)
    for r in range(GH):
        if rowcount[r] >= 2:
            for rr in range(max(0, r - padU), min(GH, r + padD + 1)):
                band.add(rr)
    # Captions hug a frame edge and OCR misses some shots, so extend the band to
    # the nearer edge: a lower-third caption blocks everything down to the bottom;
    # a top caption blocks up to the top. This covers captions OCR never saw.
    if band:
        bmin, bmax = min(band), max(band)
        bcenter = (bmin + bmax) / 2
        if bcenter >= 0.5 * GH:
            band |= set(range(bmin, GH))          # extend to bottom edge
        elif bcenter <= 0.45 * GH:
            band |= set(range(0, bmax + 1))       # extend to top edge
    caption_band_rows = sorted(band)

    def union_grids(i0, i1):
        fg = [[0.0] * GW for _ in range(GH)]
        cg = [[0.0] * GW for _ in range(GH)]
        for fi in range(i0, i1):
            or_boxes(fg, cg, frames[fi])
        for r in caption_band_rows:        # clip-wide caption band, full width
            cr = cg[r]
            for x in range(GW):
                if cr[x] < 1.0:
                    cr[x] = 1.0
        # hook band: block the top while the hook is on screen (only intervals
        # that begin before HOOK_DUR), full width, NOT edge-extended
        if HOOK_DUR > 0 and frames[i0]["t"] < HOOK_DUR:
            for r in range(0, int(HOOK_BAND * GH)):
                cr = cg[r]
                for x in range(GW):
                    if cr[x] < 1.0:
                        cr[x] = 1.0
        return fg, cg

    def centroid(fg):
        return _face_centroid(fg)

    # ---- STATIC ATTEMPT: one clean corner for the ENTIRE clip -> zero moves ----
    fg_all, cg_all = union_grids(0, n)
    cps_all = corner_placements(fg_all, cg_all)
    if cps_all:
        fcx, fcy = _face_centroid(fg_all)
        def sscore(item):
            cid, (x, y, w, h) = item
            cx = x + w / 2; cy = y + h / 2
            dist = -((cx - fcx / GW) ** 2 + (cy - fcy / GH) ** 2)
            return (dist, -(w * h))
        cid, place = sorted(cps_all.items(), key=sscore)[0]
        seg = {"x": round(place[0], 4), "y": round(place[1], 4),
               "w": round(place[2], 4), "h": round(place[3], 4),
               "visible": True, "corner": cid, "t0": 0.0, "t1": D}
        segments = [seg]
        # if the static spot sits inside the hook's top band, hide the PiP while
        # the hook is on screen instead of moving it (appear after the hook)
        if HOOK_DUR > 0 and place[1] < HOOK_BAND:
            segments = [{"x": 0, "y": 0, "w": 0, "h": 0, "visible": False,
                         "corner": None, "t0": 0.0, "t1": HOOK_DUR},
                        dict(seg, t0=HOOK_DUR)]
        out = {"pip_aspect": round(PIP_W / PIP_H, 4), "duration": d["duration"],
               "segments": segments}
        json.dump(out, open(OUT, "w"))
        print(f"{TL}: STATIC placement, 0 moves")
        for s in segments:
            tag = "show" if s["visible"] else "HIDE"
            print(f"  {s['t0']:5.2f}-{s['t1']:5.2f} {tag} x={s['x']:.2f} y={s['y']:.2f} "
                  f"w={s['w']:.2f} h={s['h']:.2f}")
        return

    raw = []
    prev_corner = None
    for k in range(nseg):
        i0, i1 = bounds[k], bounds[k + 1]
        if i1 <= i0:
            continue
        fg, cg = union_grids(i0, i1)
        cps = corner_placements(fg, cg)
        t0 = frames[i0]["t"]; t1 = frames[i1 - 1]["t"] + dt
        if cps:
            fcx, fcy = centroid(fg)
            # STABILITY: prefer the SAME corner as the previous interval — the
            # PiP only moves when its corner stops being clean. Then farthest
            # from the face; ties broken by larger size.
            def score(item):
                cid, (x, y, w, h) = item
                cx = (x + w / 2); cy = (y + h / 2)
                same = 0 if (prev_corner is None or cid == prev_corner) else 1
                dist = -((cx - fcx / GW) ** 2 + (cy - fcy / GH) ** 2)
                return (same, dist, -(w * h))
            cid, place = sorted(cps.items(), key=score)[0]
            prev_corner = cid
            raw.append({"x": round(place[0], 4), "y": round(place[1], 4),
                        "w": round(place[2], 4), "h": round(place[3], 4),
                        "visible": True, "corner": cid, "t0": t0, "t1": t1})
        else:
            # no clean corner this interval -> try a free-form clean spot, else hide
            place = search_clean(fg, cg)
            if place:
                raw.append({"x": round(place[0], 4), "y": round(place[1], 4),
                            "w": round(place[2], 4), "h": round(place[3], 4),
                            "visible": True, "corner": -1, "t0": t0, "t1": t1})
                prev_corner = None
            else:
                raw.append({"x": 0, "y": 0, "w": 0, "h": 0, "visible": False,
                            "corner": None, "t0": t0, "t1": t1})

    # merge consecutive intervals that landed on the same placement (no real hop)
    segments = []
    for s in raw:
        if segments and segments[-1]["visible"] == s["visible"] and \
           segments[-1].get("corner") == s.get("corner") and \
           abs(segments[-1]["x"] - s["x"]) < 0.03 and abs(segments[-1]["y"] - s["y"]) < 0.03:
            segments[-1]["t1"] = s["t1"]
        else:
            segments.append(dict(s))

    out = {"pip_aspect": round(PIP_W / PIP_H, 4), "duration": d["duration"],
           "segments": segments}
    json.dump(out, open(OUT, "w"))
    moves = max(0, len(segments) - 1)
    print(f"{TL}: {len(segments)} segments, {moves} move(s)")
    for s in segments:
        tag = "show" if s["visible"] else "HIDE"
        print(f"  {s['t0']:5.2f}-{s['t1']:5.2f} {tag} x={s['x']:.2f} y={s['y']:.2f} "
              f"w={s['w']:.2f} h={s['h']:.2f}")


if __name__ == "__main__":
    main()
