"""Render a NEW (batch-3+) episode end-to-end from its cleora_content row.

The original ten episodes had hand-recorded read files (reads_spec.json / read_index.json). New episodes
have only a script (Writer v2.1 beats) and a Director EDL in Supabase, so this entry point:
  1. fetches the row (script.beats + edl),
  2. takes the 4 TTS reads (hook / story / turn / closer) already generated on Higgsfield with the locked
     show voice (element f090ee08-4376-414b-9260-d6af0cbd85c8) from a small JSON handed in by the caller,
  3. cleans each read through the ElevenLabs Voice Isolator (same as the originals; key from env
     ELEVEN_KEY, never written to disk),
  4. registers the episode into build_episode's SPEC/RIDX/HOOKS/SLUG at runtime,
  5. wires the Director's clips exactly like build_from_director.py and renders through OpenMontage.

Usage: ELEVEN_KEY=... python3 build_new_episode.py <ep> <content_id> <tts.json>
  tts.json = {"hook": "<wav url>", "story": "<wav url>", "turn": "<wav url>", "closer": "<wav url>",
              "turn_at": <index of the first body beat spoken in the 'turn' read>}
"""
import sys, os, json, subprocess, re
BATCH=os.path.expanduser('~/cleora-render/cleora-batch')
sys.path.insert(0, BATCH)
import build_episode as be

EP, CID, TTS_JSON = sys.argv[1], sys.argv[2], sys.argv[3]
KEY=os.environ.get('SUPABASE_KEY','')
CA='/root/.ccr/ca-bundle.crt'
SB='https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'

def fetch_row(cid):
    r=subprocess.run(['curl','-s',f'{SB}?content_id=eq.{cid}&select=content_id,title,story_key,hook_text,script,edl,script_status',
                      '-H',f'apikey: {KEY}','-H',f'Authorization: Bearer {KEY}'],capture_output=True,text=True)
    d=json.loads(r.stdout)[0]; assert d['script_status']=='scripted', f'{cid} is {d["script_status"]}, need scripted (Director EDL)'; return d

row=fetch_row(CID); beats=row['script']['beats']; cuts=row['edl']['cuts']
if row['edl'].get('music'): be.MUSIC_PICK[EP]=row['edl']['music']; print(f"{EP}: Director assigned music {row['edl']['music']}")
tts=json.load(open(TTS_JSON))
# 'verdict' is a body beat that happens to be spoken to camera. It must ride in the reads and the
# shotmap like any other, or its line is silently dropped from both the voiceover and the captions.
BODY_SLOTS={'body','verdict'}
body=[b for b in beats if b['slot'] in BODY_SLOTS]
turn_at=int(tts.get('turn_at', max(1,int(len(body)*0.6))))
reads={'hook': beats[0]['vo'],
       'story': ' '.join(b['vo'] for b in body[:turn_at]),
       'turn':  ' '.join(b['vo'] for b in body[turn_at:]),
       'closer': beats[-1]['vo']}
assert beats[0]['slot']=='hook' and beats[-1]['slot']=='closer', 'script must start with hook and end with closer'

# ---- 1. reads: download the Higgsfield TTS wavs, clean through ElevenLabs Voice Isolator (cached)
AUD=f'{BATCH}/audio'; ISO=f'{AUD}/iso'; os.makedirs(ISO, exist_ok=True)
EL=os.environ.get('ELEVEN_KEY','')
rid={}
for k in ('hook','story','turn','closer'):
    rk=f'{EP}_{k}'; raw=f'{AUD}/{rk}.wav'; iso=f'{ISO}/{rk}.wav'; rid[k]=rk
    if not os.path.exists(raw) or os.path.getsize(raw)<1000:
        subprocess.run(['curl','-sS','-o',raw,tts[k]],check=True)
        # Higgsfield may hand back mp3/other; normalise to 44.1k mono wav
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',raw,'-ac','1','-ar','44100',raw+'.tmp.wav'],check=True)
        os.replace(raw+'.tmp.wav',raw)
    if not os.path.exists(iso) or os.path.getsize(iso)<1000:
        if False:  # isolation disabled: Higgsfield TTS is already clean; isolation was muffling it
            r=subprocess.run(['curl','-sS','-X','POST','https://api.elevenlabs.io/v1/audio-isolation',
                              '-H',f'xi-api-key: {EL}','-F',f'audio=@{raw}','-o',iso+'.mp3'],capture_output=True,text=True)
            ok = r.returncode==0 and os.path.exists(iso+'.mp3') and os.path.getsize(iso+'.mp3')>1000
            if ok:
                subprocess.run(['ffmpeg','-y','-loglevel','error','-i',iso+'.mp3','-ac','1','-ar','44100',iso],check=True)
                os.remove(iso+'.mp3')
            else:
                print(f'[warn] isolator failed for {rk}: {r.stderr[:200]} - using raw read'); subprocess.run(['cp',raw,iso],check=True)
        else:
            print(f'[warn] ELEVEN_KEY not set - using raw read for {rk}'); subprocess.run(['cp',raw,iso],check=True)

# ---- 1b. LEVEL MATCH. Higgsfield hands back reads at wildly different levels (ep460: hook -22.8 dB
# mean, story -44.5 dB - a 22 dB gap that made the story nearly inaudible and the mix pump). The
# conditioning chain in build_episode uses FIXED -45 dB silenceremove thresholds, which only behave
# on a ~-22 dB source: on a -44 dB read they eat the speech itself. So bring every read to a common
# integrated loudness here, before build_episode ever sees it. Two-pass loudnorm for accuracy.
READ_LUFS = -23.0
for k in ('hook','story','turn','closer'):
    iso = f"{ISO}/{EP}_{k}.wav"
    lvl = f"{ISO}/{EP}_{k}.lvl"
    if os.path.exists(lvl):
        continue
    m = subprocess.run(['ffmpeg','-hide_banner','-v','info','-i',iso,'-af',
                        f'loudnorm=I={READ_LUFS}:LRA=9:TP=-2:print_format=json','-f','null','-'],
                       capture_output=True, text=True)
    mm = re.search(r'\{[^{}]*"input_i"[^{}]*\}', m.stderr, re.S)
    if not mm:
        print(f'[warn] level-match measure failed for {EP}_{k} - leaving as is'); continue
    st = json.loads(mm.group(0))
    before = st.get('input_i')
    af = (f"loudnorm=I={READ_LUFS}:LRA=9:TP=-2:"
          f"measured_I={st['input_i']}:measured_LRA={st['input_lra']}:"
          f"measured_TP={st['input_tp']}:measured_thresh={st['input_thresh']}:linear=true")
    r = subprocess.run(['ffmpeg','-y','-loglevel','error','-i',iso,'-af',af,
                        '-ar','44100','-ac','1',iso+'.lvl.wav'], capture_output=True, text=True)
    if r.returncode == 0 and os.path.getsize(iso+'.lvl.wav') > 1000:
        os.replace(iso+'.lvl.wav', iso)
        open(lvl,'w').write(f'{before} -> {READ_LUFS}\n')
        print(f'{EP}: level-matched {k}: {before} LUFS -> {READ_LUFS} LUFS')
    else:
        print(f'[warn] level-match apply failed for {EP}_{k}: {r.stderr[:160]}')

# ---- 2. register the episode into build_episode's tables (runtime only, nothing written to the json files)
# on_screen_hook (Writer v5+) is a DISTINCT context-giving headline, never the spoken hook line - it must
# never be derived from beats[0]['vo']. Fall back to the old derive-from-VO behavior only for legacy rows
# written before this field existed.
hook_card=(row['script'].get('on_screen_hook') or '').strip()
if not hook_card:
    hook_card=re.sub(r',?\s*darling[.!?]*$','.',beats[0]['vo'].strip(), flags=re.I)
be.SPEC[EP]={'title':row['title'],'reads':reads}
be.RIDX[EP]=rid
be.HOOKS[EP]=hook_card
be.SLUG[EP]=re.sub(r'[^a-z0-9]+','',row['story_key'].split('_')[0]+row['story_key'].split('_')[-1])[:14] or 'story'

# ---- 3. Director wiring (mirror of build_from_director.py)
DL=f'{BATCH}/director_clips/{EP}'; os.makedirs(DL,exist_ok=True)
def dl(clip_key,url):
    p=f'{DL}/{clip_key}.mp4'
    if not os.path.exists(p) or os.path.getsize(p)<10000:
        subprocess.run(['curl','-sS','-o',p,url],check=True)
    return p
paths={c['clip_key']:dl(c['clip_key'],c['url']) for c in cuts if c.get('url')}
be.DIRECTOR_CLIPS={k:paths[k] for k in paths}
T='(in/24)'
SBASE='https://qlcmgxgwpzmiebzxflai.supabase.co/storage/v1/object/public/cleora-clips'
# OPENER SET = the owner's can_open marks in cleora_clips (review board export), rotated by episode number.
def opener_set():
    url=("https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_clips?can_open=eq.true&status=eq.active"
         "&select=shot_key,video_public_url,category&order=shot_key.asc")
    try:
        r=subprocess.run(['curl','-s',url,'-H',f'apikey: {KEY}','-H',f'Authorization: Bearer {KEY}'],capture_output=True,text=True,timeout=30)
        rows=[x for x in json.loads(r.stdout) if x.get('video_public_url')]
    except Exception as e:
        print('opener_set: catalog unreachable, using classic room shots:', e); rows=[]
    out=[]
    for x in rows:
        wide=(x.get('category') or '').lower().startswith('wide')
        out.append((x['shot_key'], x['video_public_url'], f'min(1.0+0.12*{T},1.50)' if wide else f'min(1.0+0.08*{T},1.30)'))
    return out or [('cleora_walk',   f'{SBASE}/_library/cleora_walk.mp4',    f'min(1.0+0.10*{T},1.40)'),
                   ('cleora_orb_wide',f'{SBASE}/_library/cleora_orb_wide.mp4',f'min(1.0+0.14*{T},1.55)'),
                   ('cleora_tight',  f'{SBASE}/cleora_tight.mp4',            f'min(1.0+0.12*{T},1.45)')]
OPENERS=opener_set()
_epn=int(''.join(ch for ch in EP if ch.isdigit()) or 0)
_ok,_ou,_ozx=OPENERS[_epn % len(OPENERS)]
be.OPENER_SRC[EP]=(dl(_ok,_ou), _ozx, 0.5, 0.45)
_lay=f'{BATCH}/opener_layout.json'                      # composition-aware hook card (see build_from_director)
if os.path.exists(_lay):
    _L=json.load(open(_lay)).get(_ok) or {}
    if _L.get('card_band'): be.HOOK_Y[EP]=int(_L['card_band'][0])+20; print(f'{EP}: hook card band for {_ok}: {_L["card_band"]} ({_L.get("anchor")})')

# ---- 2b. HOOK OPENER. When the Director picked one of the owner's two-shot hooks (edl.hook), the
# opener is that PAIR, not a single can_open clip. Build it here as one file with the zoom moves baked
# in and hand it to OPENER_SRC with a flat zoom, so build_episode treats it as an ordinary source.
# The pair is built to the OWNER'S EXACT SPEC - shot A from in_a for cut_a, shot B from in_b for cut_b -
# and its own length is registered as the opener slot (OPENER_LEN), so nothing downstream decides where
# the hook cuts: the spoken hook no longer stretches a short pair or overruns a long one.
_hook = (row.get('edl') or {}).get('hook') or {}
if _hook.get('shots') == 2 and _hook.get('shot_a_url') and _hook.get('shot_b_url'):
    HK = f'{BATCH}/hook_openers'; os.makedirs(HK, exist_ok=True)
    def _leg(shot, url, secs, mv, out, start=0.0):
        src = dl(shot, url)
        f = max(1, int(round(secs * 30)) - 1)
        if mv and abs(float(mv.get('zt', 1)) - float(mv.get('zf', 1))) > 0.02:
            zf, zt = float(mv['zf']), float(mv['zt'])
            fx, fy = float(mv.get('fx', 0.5)), float(mv.get('fy', 0.6))
            d = zt - zf
            z = f"{zf:.3f}{'+' if d > 0 else '-'}{abs(d):.3f}*on/{f}"
            vf = (f"fps=30,scale=2160:3840,zoompan=z='{z}':x='{fx:.2f}*iw-iw/(2*zoom)':"
                  f"y='{fy:.2f}*ih-ih/(2*zoom)':d=1:s=1080x1920:fps=30")
        else:
            vf = "fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        # -ss and -t are INPUT options: after -i they would trim the filtered result
        # instead of seeking the source, which silently discards the owner's in-point.
        _seek = ['-ss', str(round(start, 3))] if start and start > 0 else []
        subprocess.run(['ffmpeg','-y','-loglevel','error'] + _seek +
                       ['-t',str(round(secs,3)),'-i',src,'-an',
                        '-vf',vf,'-r','30','-c:v','libx264','-crf','18','-preset','medium',
                        '-pix_fmt','yuv420p',out], check=True)
        return out
    # build_episode speeds every source by 1.1x, so source seconds must be scaled up to survive as
    # the designed on-screen seconds.
    _aSrc = round(float(_hook.get('cut_a') or 2.4) * 1.1, 3)
    _bSrc = round(float(_hook.get('cut_b') or 2.5) * 1.1, 3)
    _pair = f"{HK}/{EP}_{_hook.get('hook_key') or 'pair'}.mp4"
    _inA = float(_hook.get('in_a') or 0)
    _inB = float(_hook.get('in_b') or 0)
    _a = _leg(_hook['shot_a'], _hook['shot_a_url'], _aSrc, _hook.get('move_a'),
              f'{HK}/{EP}_A.mp4', _inA * 1.1)
    _b = _leg(_hook['shot_b'], _hook['shot_b_url'], _bSrc, _hook.get('move_b'),
              f'{HK}/{EP}_B.mp4', _inB * 1.1)
    _lst = f'{HK}/{EP}_list.txt'
    open(_lst,'w').write(f"file '{os.path.basename(_a)}'\nfile '{os.path.basename(_b)}'\n")
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',_lst,
                    '-c','copy',_pair], check=True)
    be.OPENER_SRC[EP] = (_pair, '1.0', 0.5, 0.5)
    # The opener slot IS the pair. Measured, not assumed: a source that runs out before its out-point
    # would otherwise leave a slot longer than the pair, and the renderer fills by slowing.
    _pairLen = float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                                     '-of','csv=p=0',_pair],
                                    capture_output=True, text=True, check=True).stdout.strip())
    be.OPENER_LEN[EP] = _pairLen
    _want = _aSrc + _bSrc
    if _pairLen < _want - 0.05:
        print(f"{EP}: WARNING hook pair is {_pairLen/1.1:.2f}s on screen, short of the designed "
              f"{_want/1.1:.2f}s - a source clip ran out before its out-point")
    if _hook.get('hook_y'): be.HOOK_Y[EP] = int(_hook['hook_y'])
    print(f"{EP}: HOOK {_hook.get('hook_key')} = {_hook['shot_a']} -> {_hook['shot_b']} "
          f"({_hook.get('transition')}, A {_inA}s+{_hook.get('cut_a')}s, B {_inB}s+{_hook.get('cut_b')}s, "
          f"= {_pairLen/1.1:.2f}s on screen, card y={be.HOOK_Y.get(EP)})")
    print(f"{EP}: hook reason - {_hook.get('reason')}")
else:
    print(f"{EP}: no hook pair on the EDL - opening on the rotation clip {_ok}")
bodycuts=[c for c in cuts if c['slot'] in BODY_SLOTS]
closer=[c for c in cuts if c['slot']=='closer']
final=[]; fvos=[]
for c in bodycuts:
    if not final or final[-1]!=c['clip_key']: final.append(c['clip_key']); fvos.append(c.get('vo',''))
assert len(final)>=5, f'{EP}: Director handed only {len(final)} body clips'
be.SHOTMAPS[EP]=final; be.BEAT_VO[EP]=fvos
if closer: be.CLOSER_SRC[EP]=paths[closer[0]['clip_key']]
print(f'{EP} ({CID}): opener={_ok} | reads hook/story/turn/closer = {[len(reads[k].split()) for k in ("hook","story","turn","closer")]} words | body={final} | closer={closer[0]["clip_key"] if closer else "orb"}')
be.build(EP)
print(f'{EP} rendered from script + Director EDL')
