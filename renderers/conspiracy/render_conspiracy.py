#!/usr/bin/env python3
"""Conspiracy Kitchen renderer (durable home: ~/Claude/conspiracy-render/).

Data-driven: reads each story's hook + screens from Supabase, splits the hook
across the 2 opening beats, auto-distills screens into short captions, drops in
the fixed v21 BRIDGE + CTA, and rotates 3 clip ORDERS. Per-clip effects: stretch
(hold a clip longer) and crash_zoom_at (instant punch inside one clip). Every
render is wrapped by ffguard (auto-kills runaway/hanging ffmpeg).

Usage:
    python3 render_conspiracy.py --ids 62,63,64,65 --prefix BATCH4
    python3 render_conspiracy.py --ids 26 --prefix TEST --orders Order1

Reference docs (edit these, they are the source of truth):
    Character 4/EDIT RULES.md, EDIT PATTERNS.json, DEATH-HARM-WORD-GRID.md
"""
import os, re, json, subprocess, sys, argparse, urllib.request
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.ffguard import run_ffmpeg_guarded
from common import env

# Asset locations are env-overridable so the repo is portable; the defaults are
# this machine's paths so it still runs unchanged here.
SEGDIR = env.get("CONSPIRACY_SEGDIR",
                 os.path.expanduser("~/Desktop/AI Video Generation /Character 4 /Edit Segments (ready)"))
OUTDIR = env.get("CONSPIRACY_OUTDIR",
                 os.path.expanduser("~/Desktop/AI Video Generation /Character 4 /Edit"))
WORK = env.get("CONSPIRACY_WORK", os.path.join(os.path.dirname(__file__), "work"))
FONT = env.get("HOOK_FONT_OTF",
               os.path.expanduser("~/Claude/carousel-command-center/fonts/TikTokSans36pt-ExtraBold.otf"))
EMOJI_FONT = env.get("EMOJI_FONT", "/System/Library/Fonts/Apple Color Emoji.ttc")
SUPA_URL = env.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co") \
    + "/rest/v1/medical_conspiracy_stories"
SUPA_KEY = env.require("SUPABASE_ANON_KEY")
os.makedirs(WORK, exist_ok=True)

W, H = 1080, 1920
CAP_SIZE, TAG_SIZE = 60, 48
PAD_X, PAD_Y, GAP, RADIUS = 26, 14, 8, 18
BAND_CENTER_Y = 720
WRAP = 20
_emoji_strike = ImageFont.truetype(EMOJI_FONT, 160)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF\U0001F900-\U0001F9FF]️?|️")

def render_emoji(ch, target_h):
    img = Image.new("RGBA", (240, 240), (0,0,0,0))
    ImageDraw.Draw(img).text((120,120), ch, font=_emoji_strike, embedded_color=True, anchor="mm")
    bb = img.getbbox()
    if not bb: return None
    img = img.crop(bb); s = target_h/img.height
    return img.resize((max(1,int(img.width*s)), target_h), Image.LANCZOS)

def split_runs(line):
    runs, pos = [], 0
    for m in EMOJI_RE.finditer(line):
        if m.start()>pos: runs.append(("text", line[pos:m.start()]))
        if m.group()!="️": runs.append(("emoji", m.group().replace("️","")))
        pos = m.end()
    if pos<len(line): runs.append(("text", line[pos:]))
    return runs

def wrap(text, width=WRAP):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t=(cur+" "+w).strip()
        if len(EMOJI_RE.sub("",t))<=width or not cur: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    merged=[]
    for l in lines:
        if merged and not EMOJI_RE.sub("",l).strip(): merged[-1]+=" "+l
        else: merged.append(l)
    return merged

def line_box(draw, font, line):
    asc,desc=font.getmetrics(); th=asc+desc; eh=int(th*0.92)
    tot,out=0,[]
    for kind,val in split_runs(line):
        if kind=="text":
            w=draw.textlength(val,font=font); out.append(("text",val,w)); tot+=w
        else:
            em=render_emoji(val,eh)
            if em is None: continue
            w=em.width+6; out.append(("emoji_img",em,w)); tot+=w
    return tot,th,out

def make_caption_png(spec, path):
    img=Image.new("RGBA",(W,H),(0,0,0,0)); draw=ImageDraw.Draw(img)
    capf=ImageFont.truetype(FONT,CAP_SIZE); tagf=ImageFont.truetype(FONT,TAG_SIZE)
    meas=[]
    for line,style in spec:
        f=tagf if style=="tag" else capf
        w,h,runs=line_box(draw,f,line); meas.append((line,style,f,w,h,runs))
    total=sum(h+2*PAD_Y for *_,h,_ in meas)+GAP*(len(meas)-1)
    y=BAND_CENTER_Y-total//2
    for line,style,f,w,h,runs in meas:
        bw=w+2*PAD_X; x0=(W-bw)//2; box=[x0,y,x0+bw,y+h+2*PAD_Y]
        if style=="tag": draw.rounded_rectangle(box,RADIUS,fill=(17,17,17,255)); fill=(255,255,255,255)
        else: draw.rounded_rectangle(box,RADIUS,fill=(255,255,255,255)); fill=(10,10,10,255)
        cx=x0+PAD_X
        for it in runs:
            if it[0]=="text": draw.text((cx,y+PAD_Y),it[1],font=f,fill=fill); cx+=it[2]
            else: img.paste(it[1],(int(cx)+3,y+PAD_Y+(h-it[1].height)//2),it[1]); cx+=it[2]
        y=box[3]+GAP
    img.save(path)

def probe_dur(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path],
                     capture_output=True,text=True)
    return float(r.stdout.strip())

def render(edl, out_name):
    segs=[]; t=0.0; capfiles=[]; pre=[]; concat_lbls=[]
    for i,beat in enumerate(edl):
        segpath=os.path.join(SEGDIR,beat["seg"]); segs.append(segpath)
        dur=probe_dur(segpath)
        stretch=float(beat.get("stretch",1.0)); eff=dur*stretch
        ops=[]
        if stretch!=1.0: ops+=[f"setpts=PTS*{stretch}","fps=30"]
        cz=beat.get("crash_zoom_at")
        if cz is not None:
            amt=float(beat.get("cz_amt",0.05)); f0=int(round(cz*30*stretch))
            ops.append(f"zoompan=z='if(lt(on,{f0}),1,{1+amt:.4f})':"
                       f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps=30")
        if ops:
            pre.append(f"[{i}:v]"+",".join(ops)+f"[c{i}]"); concat_lbls.append(f"c{i}")
        else:
            concat_lbls.append(f"{i}:v")
        cap=beat.get("caption")
        if cap:
            spec=[]
            if beat.get("brand_tag"): spec.append(('Health "They" Hide \U0001F441️',"tag"))
            spec+=[(l,"cap") for l in wrap(cap)]
            cp=os.path.join(WORK,f"{out_name}_cap{i:02d}.png"); make_caption_png(spec,cp)
            capfiles.append((cp, round(t,3), round(t+eff,3)))
        t+=eff
    total=t
    cmd=["ffmpeg","-y","-loglevel","error"]
    for s in segs: cmd+=["-i",s]
    for cp,_,_ in capfiles: cmd+=["-loop","1","-i",cp]
    n=len(segs)
    parts=list(pre)
    parts.append("".join(f"[{l}]" for l in concat_lbls)+f"concat=n={n}:v=1:a=0[base]")
    cur="base"
    for j,(cp,s,e) in enumerate(capfiles):
        nxt=f"v{j}"; parts.append(f"[{cur}][{n+j}:v]overlay=0:0:enable='between(t,{s},{e})'[{nxt}]"); cur=nxt
    parts.append(f"[{cur}]format=yuv420p[vout]")
    fc=";".join(parts)
    out=os.path.join(OUTDIR,out_name)
    cmd+=["-filter_complex",fc,"-map","[vout]","-t",f"{total:.2f}",
          "-c:v","libx264","-crf","20","-preset","veryfast","-r","30","-movflags","+faststart",out]
    run_ffmpeg_guarded(cmd, out, expected_seconds=total)
    print(f"{out_name}: {total:.1f}s -> {out}")
    return out, total

# ===== FIXED v21 back-half (identical every video) =====
BRIDGE = [
 "My own doctors knew I was suffering from high BMI and blood pressure.",
 "They hid that there was a peptide out there that could save my life.",
 "I found a Harvard study. Black women responded best to peptides.",
 "But we're the least prescribed.",
]
CTA = "Type RENEW for the quiz that matches Black women to the right peptide. \U0001F447"

# ===== The 3 clip orders as ROLE templates (seg, role, effects) =====
ORDERS = {
 "Order1": [  # Classic — she's cooking from frame 1
   ("01 - stir open - 3.0s.mp4",   "hook1",   {"brand_tag":True,"crash_zoom_at":1.5}),
   ("02 - stand at pot - 1.5s.mp4","hook2",   {"stretch":1.5}),
   ("03 - empty room A - 3.5s.mp4","story0",  {}),
   ("05 - stir long - 3.5s.mp4",   "story1",  {}),
   ("06 - stares - 3.5s.mp4",      "story2",  {}),
   ("04 - salt wipe - 3.0s.mp4",   "story3",  {}),
   ("07 - empty room B - 5.8s.mp4","bridge0", {}),
   ("08 - enters room - 4.0s.mp4", "bridge1", {}),
   ("09 - smiles - 3.6s.mp4",      "bridge2", {}),
   ("10 - stir short - 4.0s.mp4",  "bridge2", {}),
   ("11 - inhale smell - 3.5s.mp4","bridge3", {}),
   ("12 - point up CTA - 6.0s.mp4","cta",     {"cta":True}),
 ],
 "Order2": [  # Cold open — empty room hook, she appears on beat 2
   ("03 - empty room A - 3.5s.mp4","hook1",   {"brand_tag":True}),
   ("01 - stir open - 3.0s.mp4",   "hook2",   {"crash_zoom_at":1.5}),
   ("02 - stand at pot - 1.5s.mp4","story0",  {}),
   ("04 - salt wipe - 3.0s.mp4",   "story1",  {}),
   ("06 - stares - 3.5s.mp4",      "story2",  {}),
   ("05 - stir long - 3.5s.mp4",   "story3",  {}),
   ("07 - empty room B - 5.8s.mp4","bridge0", {}),
   ("08 - enters room - 4.0s.mp4", "bridge1", {}),
   ("10 - stir short - 4.0s.mp4",  "bridge2", {}),
   ("09 - smiles - 3.6s.mp4",      "bridge2", {}),
   ("11 - inhale smell - 3.5s.mp4","bridge3", {}),
   ("12 - point up CTA - 6.0s.mp4","cta",     {"cta":True}),
 ],
 "Order3": [  # Eye contact first — jump-cut hook then she locks eyes
   ("01 - stir open - 3.0s.mp4",   "hook1",   {"brand_tag":True,"crash_zoom_at":1.5}),
   ("02 - stand at pot - 1.5s.mp4","hook2",   {"stretch":1.5}),
   ("06 - stares - 3.5s.mp4",      "story0",  {}),
   ("03 - empty room A - 3.5s.mp4","story1",  {}),
   ("05 - stir long - 3.5s.mp4",   "story2",  {}),
   ("04 - salt wipe - 3.0s.mp4",   "story3",  {}),
   ("07 - empty room B - 5.8s.mp4","bridge0", {}),
   ("08 - enters room - 4.0s.mp4", "bridge1", {}),
   ("09 - smiles - 3.6s.mp4",      "bridge2", {}),
   ("10 - stir short - 4.0s.mp4",  "bridge2", {}),
   ("11 - inhale smell - 3.5s.mp4","bridge3", {}),
   ("12 - point up CTA - 6.0s.mp4","cta",     {"cta":True}),
 ],
}

def resolve(role, story):
    if role == "hook1": return story["hook1"]
    if role == "hook2": return story["hook2"]
    if role.startswith("story"): return story["story"][int(role[-1])]
    if role.startswith("bridge"): return BRIDGE[int(role[-1])]
    if role == "cta": return CTA
    raise ValueError(role)

def build_edl(order_name, story):
    edl=[]
    for seg, role, fx in ORDERS[order_name]:
        beat={"seg":seg, "caption":resolve(role, story)}
        beat.update(fx)
        edl.append(beat)
    return edl

# ===== DB fetch + automatic hook split + caption distillation =====
def fetch_stories(ids):
    q = SUPA_URL + "?select=id,title,script&id=in.(" + ",".join(str(i) for i in ids) + ")"
    req = urllib.request.Request(q, headers={"apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

_ABBR = ['Dr','Mr','Mrs','Ms','St','Jr','Sr','vs','etc','Inc','Co','No','Gen','Sen','Rep','Gov','Lt','Sgt']
def sentences(text):
    t = (text or "").strip()
    for a in _ABBR:
        t = re.sub(r'\b' + a + r'\.', a + '<DOT>', t)
    t = re.sub(r'\b([A-Z])\.', r'\1<DOT>', t)
    t = re.sub(r'(\d)\.(\d)', r'\1<DOT>\2', t)
    parts = re.split(r'(?<=[.!?])\s+', t)
    return [p.replace('<DOT>', '.').strip() for p in parts if p.strip()]

def split_hook(hook):
    hook = (hook or "").strip()
    sents = sentences(hook)
    if len(sents) >= 2:
        return sents[0], " ".join(sents[1:])
    h = sents[0] if sents else hook
    m = re.search(r'\s(and|but|then|so)\s', h, re.I)
    if m and m.start() >= 12:
        return h[:m.start()].strip(), h[m.start():].strip()
    w = h.split()
    if len(w) < 5: return h, ""
    mid = (len(w) + 1) // 2
    return " ".join(w[:mid]), " ".join(w[mid:])

def distill(screen, max_words=15):
    screen = (screen or "").strip()
    sents = sentences(screen)
    if not sents: return screen
    first = sents[0]; w = first.split()
    if len(w) <= max_words:
        if len(sents) > 1 and len(w) + len(sents[1].split()) <= max_words:
            return first + " " + sents[1]
        return first
    trunc = " ".join(w[:max_words])
    if "," in trunc: return trunc[:trunc.rfind(",")].rstrip() + "."
    return trunc.rstrip(".,;:") + "."

def sanitize(title):
    t = re.sub(r'[^A-Za-z0-9 ]+', ' ', title or 'story').strip()
    return re.sub(r'\s+', ' ', t)[:48]

def main():
    ap = argparse.ArgumentParser(description="Render conspiracy-kitchen videos from DB story ids.")
    ap.add_argument("--ids", required=True, help="comma-separated story ids, e.g. 62,63,64")
    ap.add_argument("--prefix", default="RENDER", help="output filename prefix (e.g. BATCH5)")
    ap.add_argument("--orders", default="Order1,Order2,Order3", help="orders to rotate across ids")
    a = ap.parse_args()
    ids = [int(x) for x in a.ids.split(",") if x.strip()]
    orders = [o.strip() for o in a.orders.split(",") if o.strip()]
    rows = fetch_stories(ids)
    by_id = {int(r["id"]): r for r in rows}
    done = 0; fails = []
    for idx, sid in enumerate(ids):
        r = by_id.get(sid)
        if not r: fails.append((sid, "not found")); continue
        sc = r.get("script") or {}
        screens = sc.get("screens") or []
        if len(screens) < 4: fails.append((sid, "<4 screens")); continue
        h1, h2 = split_hook(sc.get("hook", ""))
        story = {"hook1": h1, "hook2": h2, "story": [distill(screens[k]) for k in range(4)]}
        order = orders[idx % len(orders)]
        out = f"{a.prefix} - {sanitize(r.get('title'))} - {order}.mp4"
        try:
            render(build_edl(order, story), out); done += 1
            print(f"  [{done}/{len(ids)}] {sid} {order}")
        except Exception as e:
            fails.append((sid, str(e)[:80]))
    print(f"DONE: {done}/{len(ids)} rendered; fails={fails}")

if __name__ == "__main__":
    main()
