"""
Shared detection library for the dating-reaction pipeline.

One source of truth for face detection (YuNet + multi-cue gate) and caption-text
detection, used by the timeline analyzer, the placement solver, and the debug
overlay so they never drift apart.

Boxes are returned in PIXEL coords of the frame passed in. Callers that need
resolution-independent values normalize by frame width/height.
"""
import os
import cv2
import pytesseract
from pytesseract import Output

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_YUNET = os.path.join(_SCRIPT_DIR, "yunet.onnx")

# Gate defaults (validated across 7 library rows).
FACE_SCORE = 0.80
BOTTOM_REJECT = 0.25
MIN_FACE_FRAC = 0.05
TEXT_MIN_CONF = 60
TEXT_MIN_HEIGHT_FRAC = 0.02


def load_detector(yunet_path=DEFAULT_YUNET, cand_score=0.5):
    if not os.path.exists(yunet_path):
        return None
    return cv2.FaceDetectorYN.create(yunet_path, "", (320, 320), cand_score, 0.3, 5000)


def landmark_valid(f):
    """f = YuNet row: [x,y,w,h, rex,rey, lex,ley, nx,ny, rmx,rmy, lmx,lmy, score]."""
    x, y, w, h = f[:4]
    re = (f[4], f[5]); le = (f[6], f[7]); nt = (f[8], f[9])
    rcm = (f[10], f[11]); lcm = (f[12], f[13])
    eye_dx = abs(re[0] - le[0]); eye_dy = abs(re[1] - le[1])
    ed = (eye_dx ** 2 + eye_dy ** 2) ** 0.5
    if not ((re[1] + le[1]) / 2 < nt[1] < (rcm[1] + lcm[1]) / 2):
        return False
    if ed > 0 and eye_dy > 0.45 * ed:
        return False
    if not (0.20 * w <= eye_dx <= 0.95 * w):
        return False
    lo, hi = sorted([re[0], le[0]])
    if not (lo - 0.15 * w <= nt[0] <= hi + 0.15 * w):
        return False
    if not (0.85 <= h / w <= 1.9):
        return False
    return True


def gate_reason(f, frame_h, frame_w,
                face_score=FACE_SCORE, bottom_reject=BOTTOM_REJECT,
                min_face_frac=MIN_FACE_FRAC):
    """Return None if the candidate is an accepted face, else a reject reason."""
    x, y, w, h = f[:4]
    if w < min_face_frac * frame_w or h < min_face_frac * frame_w:
        return "size"
    if float(f[-1]) < face_score:
        return "score"
    if (y + h / 2) > (1.0 - bottom_reject) * frame_h:
        return "bottom"
    if not landmark_valid(f):
        return "landmark"
    return None


def detect_faces(detector, frame, **gate_kw):
    """Return list of accepted (x, y, w, h, score) in pixel coords."""
    if detector is None:
        return []
    h, w = frame.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(frame)
    out = []
    if faces is not None:
        for f in faces:
            if gate_reason(f, h, w, **gate_kw) is None:
                out.append((int(f[0]), int(f[1]), int(f[2]), int(f[3]), float(f[-1])))
    return out


def detect_text(frame, min_conf=TEXT_MIN_CONF, min_height_frac=TEXT_MIN_HEIGHT_FRAC):
    """Return list of caption-like (x, y, w, h) text boxes in pixel coords."""
    h = frame.shape[0]
    data = pytesseract.image_to_data(frame, output_type=Output.DICT, config="--psm 11")
    out = []
    for i in range(len(data["text"])):
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        t = data["text"][i].strip()
        if conf < min_conf or len(t) < 3:
            continue
        if sum(c.isalpha() for c in t) < len(t) * 0.6:
            continue
        if data["height"][i] < min_height_frac * h:
            continue
        out.append((data["left"][i], data["top"][i], data["width"][i], data["height"][i]))
    return out
