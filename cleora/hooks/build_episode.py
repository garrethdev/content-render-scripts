import subprocess, os, json, sys, re
sys.path.insert(0,'/home/user/calesthio/openmontage')
from lib.checkpoint import init_project, write_checkpoint, PROJECTS_DIR
import jsonschema, whisper
BATCH='/home/user/calesthio/openmontage/projects/cleora-batch'
EP1A='/home/user/calesthio/openmontage/projects/cleora-ep01-rooftops/assets'
run=lambda c: subprocess.run(c, check=True)
def dur_of(f): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(f)],capture_output=True,text=True).stdout)
def validate(name,obj):
    jsonschema.validate(obj, json.load(open(f'/home/user/calesthio/openmontage/schemas/artifacts/{name}.schema.json'))); return obj

SPEC=json.load(open(f'{BATCH}/reads_spec.json'))
HOOKS=json.load(open(f'{BATCH}/hooks.json'))
RIDX=json.load(open(f'{BATCH}/read_index.json'))   # ep -> {read_key: rNN}
# library clip -> (source_dur, tx, ty) zoom targets from ep01 study; new b-roll centers
LIB={'lib_wide_purple_orb':(4.086,0.42,0.44),'shot3_flip':(6.042,0.60,0.50),'shot4_sanatorium':(6.042,0.60,0.55),
 'lib_the_ward':(4.625,0.50,0.36),'still_sanatorium_kb':(4.0,0.47,0.55),'lib_the_healing':(5.042,0.38,0.60),
 'shot7_ledger':(11.042,0.50,0.45),'shot9_pills':(5.042,0.45,0.55),'lib_the_curtain_drawn':(5.042,0.42,0.55),
 'lib_the_buried_records':(5.042,0.45,0.52),'lib_the_taking':(5.042,0.47,0.45),'lib_the_peptide_vial':(5.042,0.50,0.70)}
BROLL={'ship_deck':'b100','lemon_crate':'b101','ancient_book':'b102','wormwood':'b103','flask_drink':'b104',
 'wash_basin':'b105','salt_sugar':'b106','rice_bowls':'b107','ditch_weed':'b108','sugar_bowl':'b109',
 'pink_flower':'b110','harbor':'b111','scratch':'b112',
 # expanded narrative library (b115-b126): establishment/rejection/greed/recovery/suppression beats
 'doctor_patient':'b115','man_rejected':'b116','man_leaving':'b117','council_dismiss':'b118',
 'coins_greed':'b119','patient_recovers':'b120','ledger_slam':'b121','sick_ward':'b122',
 'discoverer_candle':'b123','forgotten_portrait':'b124','refuse_bottle':'b125','whisper_council':'b126'}
SHOTMAPS={  # per ep: ordered clips between opener and closer - distributed over body.
            # RULE: no shot may repeat back-to-back; asserted in build() below.
 'ep02':['ship_deck','shot7_ledger','lemon_crate','lib_the_buried_records','lib_the_curtain_drawn','discoverer_candle'],
 'ep03':['lib_the_healing','shot9_pills','ancient_book','wormwood','lib_the_peptide_vial','lib_the_taking'],
 # ep04 ulcers/Marshall — laughed out of the room, drank the germs, won the Nobel
 'ep04':['doctor_patient','man_rejected','flask_drink','man_leaving','patient_recovers','shot7_ledger'],
 # ep05 hands/Semmelweis — rejected, mocked, died in an asylum, later vindicated
 'ep05':['sick_ward','wash_basin','man_rejected','council_dismiss','man_leaving','forgotten_portrait'],
 'ep06':['lib_the_healing','salt_sugar','lib_the_ward','lib_the_taking','shot7_ledger'],
 # ep07 rice/Takaki — navy proved it, army dismissed it out of pride, 27,000 died
 'ep07':['sick_ward','rice_bowls','ship_deck','council_dismiss','discoverer_candle','patient_recovers'],
 # ep08 ditchweed/metformin — shelved 30 years in a drawer, greed kept the cure buried
 'ep08':['doctor_patient','ditch_weed','ledger_slam','whisper_council','coins_greed','forgotten_portrait'],
 'ep09':['lib_the_ward','sugar_bowl','shot7_ledger','lib_the_buried_records','lib_the_curtain_drawn'],
 'ep10':['lib_the_healing','pink_flower','lib_the_peptide_vial','patient_recovers','coins_greed'],
 # ep11 onesimus/smallpox — knowledge from a rejected man, establishment fought it
 'ep11':['harbor','man_rejected','council_dismiss','man_leaving','sick_ward','discoverer_candle']}
CAPTIONS={
 'ep02':[('scurvy','SCURVY','w'),('james','JAMES LIND, 1747','y'),('lemons','LEMONS','y'),('forty','FORTY YEARS','w'),('limes','CHEAPER LIMES','y'),('fruit','ONE FRUIT','y')],
 'ep03':[('malaria','MALARIA','w'),('youyou','TU YOUYOU','y'),('wormwood','SWEET WORMWOOD','y'),('cold','SOAK IT COLD','w'),('artemisinin','ARTEMISININ','y'),('anonymous','ANONYMOUS FOR 30 YEARS','y')],
 'ep04':[('ulcers','STOMACH ULCERS','w'),('tagamet','TAGAMET','y'),('marshall','BARRY MARSHALL','y'),('swallowed','HE DRANK IT','w'),('business','A SUBSCRIPTION','y'),('nobel','NOBEL PRIZE, 2005','y')],
 'ep05':[('vienna','VIENNA, 1847','y'),('fever','CHILDBED FEVER','w'),('semmelweis','IGNAZ SEMMELWEIS','y'),('chlorine','WASH YOUR HANDS','w'),('asylum','DIED IN AN ASYLUM','y'),('washed','BUILT ON WASHED HANDS','y')],
 'ep06':[('cholera','CHOLERA','w'),('insulting','ALMOST INSULTING','y'),('stirred','SALT + SUGAR + WATER','y'),('bangladesh','BANGLADESH, 1971','y'),('recipe','A KITCHEN RECIPE','w'),('salesmen','FEWEST SALESMEN','y')],
 'ep07':[('beriberi','BERIBERI','w'),('takaki','TAKAKI KANEHIRO','y'),('husk','IT LIVES IN THE HUSK','y'),('prestige','WHITE RICE = PRESTIGE','w'),('thousand','27,000 SOLDIERS DIED','y'),('throwing','THROWN AWAY','y')],
 'ep08':[('diabetes','DIABETES','w'),('lilac','FRENCH LILAC','y'),('sugar','IT LOWERS BLOOD SUGAR','y'),('drawer','30 YEARS IN A DRAWER','w'),('metformin','METFORMIN','y'),('ditch','STILL IN THE DITCH','y')],
 'ep09':[('gangrene','GANGRENE','w'),('sugar','PLAIN SUGAR','y'),('knutson','DR. KNUTSON, 1981','y'),('five','605 WOUNDS HEALED','y'),('lobby','NO LOBBY','w'),('neglect','ON PURPOSE','y')],
 'ep10':[('leukemia','CHILDHOOD LEUKEMIA','w'),('madagascar','MADAGASCAR','y'),('periwinkle','ROSY PERIWINKLE','y'),('vincristine','VINCRISTINE','y'),('eli','ELI LILLY','w'),('cent','NOT A CENT','y')],
 'ep11':[('smallpox','SMALLPOX, 1721','w'),('onesimus','ONESIMUS','y'),('cotton','COTTON MATHER','y'),('inoculation','INOCULATION','y'),('fifty','1 IN 7 ... 1 IN 50','y'),('erased','NEARLY ERASED','w')]}
SLUG={'ep02':'lemons','ep03':'wormwood','ep04':'ulcers','ep05':'hands','ep06':'salt','ep07':'rice','ep08':'ditchweed','ep09':'sugarbowl','ep10':'periwinkle','ep11':'onesimus'}
# opener rotation: orb = classic wide orb shot; rise = low-angle rising to her; walk = she walks to her chair
OPENER={'ep03':'rise','ep06':'rise','ep09':'rise','ep04':'walk','ep07':'walk','ep10':'walk'}  # others default 'orb'
# Director-driven overrides (populated by build_from_director.py when using the deployed n8n Director's EDL):
DIRECTOR_CLIPS={}   # clip_key -> local downloaded path (resolver checks this first)
OPENER_SRC={}       # ep -> (src_path_or_None, zoom_expr, tx, ty) for the Director's hook clip
CLOSER_SRC={}       # ep -> local path for the Director's closer clip (else orb closer)
HOOK_Y={}           # ep -> y (px, 1080x1920) for the top of the hook card; from the opener's composition
OPENER_LEN={}       # ep -> plan-timeline seconds the opener slot must run. Set by the wrapper when the
                    # opener is the OWNER'S two-shot hook pair: the pair plays at its designed cut_a+cut_b
                    # and nothing else decides where it cuts.
                    #        analysis (opener_layout.json: face/orb-free band). Default 300 when unknown.
BEAT_VO={}          # ep -> [body-beat VO text, ...] (same order/len as SHOTMAPS[ep]); when set, each
                    #        Director clip is cut in at the whisper timestamp of its beat's spoken line
                    #        instead of even clock-division (fixes shot drift off the narration).
# whisper mishears proper nouns; alternates tried in order, '*' suffix = prefix match,
# search is anchored after the previously-found caption so loose alternates stay safe
ALT={'youyou':['youyou','yoyo','yo-yo','yo','tu','too'],'artemisinin':['artemisinin','artemis*','artemi*'],
 'tagamet':['tagamet','taga*','tag*'],'semmelweis':['semmelweis','semmel*','semel*','somm*','ignat*','ignaz*','sem*'],
 'cholera':['cholera','calera','collera','colera','kolera','kalera'],'beriberi':['beriberi','berry','barry','beri*'],
 'thousand':['thousand','thousands','27,000','27000','27','000'],'pride':['pride','prized','proud','tried','pried'],
 'salesmen':['salesmen','salesman','sales*'],'forty':['forty','40'],'limes':['limes','lime','lyme*','lines','line'],
 'fifty':['fifty','50','fiftieth'],'throwing':['throwing','throwin*','threw'],
 'cent':['cent','sent','scent'],'onesimus':['onesimus','ones*','anesim*','vanessa','seamus','simus*','named'],
 'five':['five','605'],'knutson':['knutson','knut*','newt*'],'madagascar':['madagascar','madagas*'],
 'vincristine':['vincristine','vincris*','vin*'],'takaki':['takaki','taka*'],'marshall':['marshall','marshal*'],
 'lilac':['lilac','lila*','lyla*'],'metformin':['metformin','metform*'],'gangrene':['gangrene','gangree*','gang*']}
YEL=r'\c&H3DD5FF&'; WHI=r'\c&HFFFFFF&'
FP='/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
RNMODEL=f'{BATCH}/audio_models/bd.rnnn'          # RNNoise neural denoiser (voice cleanup)
MUSIC=f'{BATCH}/assets_music/music_bed.wav'      # composed Golden-Brown-esque bed (default)
# MUSIC ROTATION: if assets_music/beds_selected.json exists (a list of bed filenames the owner picked),
# each episode takes one by episode number so the catalogue does not share a single bed.
MUSIC_PICK={}   # ep -> bed filename the DIRECTOR assigned (cleora_content.edl.music); wrappers fill this at runtime
def music_for(ep):
    pick=MUSIC_PICK.get(ep)
    if pick and os.path.exists(f'{BATCH}/assets_music/{pick}'): return f'{BATCH}/assets_music/{pick}'
    if pick: print(f'{ep}: Director music {pick} not in assets_music, falling back to rotation')
    sel=f'{BATCH}/assets_music/beds_selected.json'
    try:
        beds=[b for b in json.load(open(sel)) if os.path.exists(f'{BATCH}/assets_music/{b}')]
    except Exception:
        beds=[]
    if not beds: return MUSIC
    n=int(''.join(ch for ch in ep if ch.isdigit()) or 0)
    return f'{BATCH}/assets_music/{beds[n % len(beds)]}'
WMODEL=None
def wmodel():
    global WMODEL
    if WMODEL is None: WMODEL=whisper.load_model('base')
    return WMODEL

def build(ep):
    slug=SLUG[ep]; PID=f'cleora-{ep}-{slug}'
    pdir=init_project(PID, title=f'Madame Cleora {ep.upper()} - {SPEC[ep]["title"]}', pipeline_type='hybrid')
    A=pdir/'assets'; ART=pdir/'artifacts'; REN=pdir/'renders'
    reads=SPEC[ep]['reads']; keys=list(reads.keys())
    # 1. condition reads (gentle trim, loudnorm, click fades)
    # hook: short 0.15 fade-in (0.40 read as mumbling by review), tighter internal pauses, +6% tempo
    for k in keys:
        # source = ElevenLabs Voice-Isolator-cleaned read (static/room noise already stripped,
        # her voice preserved). Falls back to raw only if a cache file is missing.
        iso=f"{BATCH}/audio/iso/{RIDX[ep][k]}.wav"
        src=iso if os.path.exists(iso) else f"{BATCH}/audio/{RIDX[ep][k]}.wav"
        fin=0.15 if k=='hook' else 0.025
        ssil='0.30' if k=='hook' else '0.45'
        extra=',atempo=1.06' if k=='hook' else ''
        # light de-rumble only (isolator did the denoise), then trim/normalize + click fades
        run(['ffmpeg','-y','-loglevel','error','-i',src,'-af',
            f'highpass=f=85,'
            f'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.10:stop_periods=-1:stop_threshold=-45dB:stop_silence={ssil},'
            'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse'
            f'{extra},loudnorm=I=-19:LRA=9:TP=-2,afade=t=in:d={fin}',str(A/f'R_{k}.wav')])
        d=dur_of(A/f'R_{k}.wav')
        run(['ffmpeg','-y','-loglevel','error','-i',str(A/f'R_{k}.wav'),'-af',f'afade=t=out:st={max(0,d-0.05)}:d=0.05','-ar','44100',str(A/f'R_{k}_f.wav')])
    D={k:dur_of(A/f'R_{k}_f.wav') for k in keys}
    DT={t:dur_of(f'{EP1A}/tic_{t}_m.wav') for t in ['mmm','mmhm','hmhm']}
    # 2. layout: hook starts near 0, no hum before setup (review: opening dead air);
    #    hums kept before turn and closer
    body=[k for k in keys if k not in ('hook','closer')]
    ev=[]; t=0.35; starts={}
    starts['hook']=t; ev.append((str(A/'R_hook_f.wav'),t)); t+=D['hook']
    t+=0.15
    for i,k in enumerate(body):
        if k=='turn':
            t+=0.05; ev.append((f'{EP1A}/tic_hmhm_m.wav',t)); t+=DT['hmhm']; t+=0.12
        starts[k]=t; ev.append((str(A/f'R_{k}_f.wav'),t)); t+=D[k]; t+=0.20
    t+=0.02; ev.append((f'{EP1A}/tic_mmhm_m.wav',t)); t+=DT['mmhm']; t+=0.15
    starts['closer']=t; ev.append((str(A/'R_closer_f.wav'),t)); t+=D['closer']
    total=t+0.45
    inputs=[]; filt=[]
    for i,(f,st) in enumerate(ev):
        inputs+=['-i',f]; filt.append(f'[{i}:a]adelay={int(st*1000)}|{int(st*1000)}[a{i}]')
    n=len(ev)
    # VOICE-ONLY bed (no pink room tone anymore — music fills the space, and denoise already
    # cleaned the reads). Slightly hotter target (-16) so she sits clearly above the music.
    mix=''.join(f'[a{i}]' for i in range(n))+f'amix=inputs={n}:normalize=0,acompressor=threshold=-18dB:ratio=2.5:attack=12:release=180,loudnorm=I=-16:LRA=11:TP=-1.5,afade=t=out:st={total-0.7}:d=0.7,apad=whole_dur={total}[out]'
    run(['ffmpeg','-y','-loglevel','error']+inputs+['-filter_complex',';'.join(filt)+';'+mix,'-map','[out]','-ar','44100','-t',str(total),str(A/'vo_master.wav')])
    # whisper the master ONCE (natural timeline) — reused for beat-time shot alignment AND captions
    _wr=wmodel().transcribe(str(A/'vo_master.wav'), word_timestamps=True, language='en')
    WORDS=[{'w':w['word'].strip().lower().strip('.,!?…'),'s':round(w['start'],2),'e':round(w['end'],2)} for sg in _wr['segments'] for w in sg.get('words',[])]
    # SCRIPT<->WHISPER TOKEN ALIGNMENT, one pass, reused by the beat-time shot alignment AND the captions.
    # Every script token gets a start/end time from the whisper words (difflib, gaps interpolated).
    import difflib
    gt=[]; gbrk=[]; gkey=[]                              # ground-truth tokens, phrase-break flag, read key
    for k in sorted(keys, key=lambda kk: starts.get(kk,0)):
        for m in re.finditer(r"([A-Za-z0-9']+)([.,;:!?…]*)", reads[k]):
            gt.append(m.group(1)); gbrk.append(bool(m.group(2))); gkey.append(k)
    whl=[x['w'] for x in WORDS]; gtl=[w.lower() for w in gt]
    gtime=[None]*len(gt); gend=[None]*len(gt)
    for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=gtl,b=whl,autojunk=False).get_opcodes():
        if tag in ('equal','replace'):
            n=i2-i1; m=j2-j1
            for off in range(n):
                jj=j1+((min(m-1,(off*m)//n)) if (n and m) else 0)
                if 0<=jj<len(WORDS): gtime[i1+off]=WORDS[jj]['s']; gend[i1+off]=WORDS[jj]['e']
    matched=sum(1 for t in gtime if t is not None)
    good_align = matched>=max(6,int(0.4*len(gt)))
    if good_align:
        idxs=[i for i,t in enumerate(gtime) if t is not None]
        for a in range(len(idxs)-1):                   # linear-interpolate the gaps between anchors
            i0,i1_=idxs[a],idxs[a+1]; t0,t1=gtime[i0],gtime[i1_]
            for kk in range(i0+1,i1_): gtime[kk]=t0+(t1-t0)*(kk-i0)/(i1_-i0)
        for i in range(len(gtime)):
            if gtime[i] is None: gtime[i]=gtime[i-1] if (i>0 and gtime[i-1] is not None) else 0.0
            if gend[i] is None: gend[i]=gtime[i]+0.30
    print(f'{ep}: script/whisper alignment {matched}/{len(gt)} tokens matched ({"ok" if good_align else "WEAK - whisper fallback"})')
    # final-speed voice (this timeline drives captions + video); music is added at natural tempo after
    run(['ffmpeg','-y','-loglevel','error','-i',str(A/'vo_master.wav'),'-af','atempo=1.1','-ar','48000',str(A/'vo_voice.wav')])
    tfin=dur_of(A/'vo_voice.wav')
    # music bed conditioning (SOURCE PREP): loop to length, fade in 2.0 / out 2.8, and loudnorm the
    # bed to a fixed quiet target so it sits ~18 dB under her -14 LUFS voice (sound-design.md: music
    # 18-20 dB below dialogue). This is the ONLY place the raw bed is leveled; the MIX itself goes
    # through OpenMontage's AudioMixer below.
    MUSIC_LUFS=-34
    _bed=music_for(ep); print(f'{ep}: music bed {os.path.basename(_bed)}')
    run(['ffmpeg','-y','-loglevel','error','-stream_loop','-1','-i',_bed,'-t',str(round(tfin,3)),'-af',
        f'afade=t=in:d=2.0,afade=t=out:st={round(max(0,tfin-2.8),3)}:d=2.8,loudnorm=I={MUSIC_LUFS}:LRA=9:TP=-3',
        '-ar','48000',str(A/'music_ep.wav')])
    # MIX THROUGH OPENMONTAGE: AudioMixer.full_mix layers her voice + the quiet music bed and
    # normalizes the whole thing to -14 LUFS (TikTok). Ducking is OFF so the bed stays steady and
    # never pumps under her near-continuous narration (aggressive ducking under continuous VO was the
    # earlier "music vanished" bug); the bed is already ~18 dB under her, so it sits low without a duck.
    from tools.audio.audio_mixer import AudioMixer
    amres=AudioMixer().execute({"operation":"full_mix","tracks":[
        {"path":str(A/'vo_voice.wav'),"role":"speech","volume":1.0},
        {"path":str(A/'music_ep.wav'),"role":"music","volume":1.0}],
        "ducking":{"enabled":False},"normalize":True,"loudnorm_target":-14,
        "target_duration":round(tfin,3),"output_path":str(A/'vo_final.wav')})
    assert amres.success, f'AudioMixer full_mix failed: {amres.error}'
    # 3. shot boundaries: opener holds into first body read; body shots distributed; closer shot at closer start
    c1=starts[body[0]]+0.35
    c_end=total-0.10; cl_start=starts['closer']-0.55
    shots=SHOTMAPS[ep]
    # RULE: never place the same shot back-to-back (adjacent repeats read as a stutter)
    for _i in range(1,len(shots)):
        assert shots[_i]!=shots[_i-1], f'{ep}: shot {shots[_i]!r} repeats back-to-back at position {_i}'
    if ep in BEAT_VO and len(BEAT_VO[ep])==len(shots):
        # BEAT-TIME ALIGNMENT: pin each Director clip to the moment its beat's line is spoken. Clips are
        # already in narration order (Director emits beats in order + beats are built from reads_spec =
        # the recorded audio), so we DON'T re-sort - we walk forward, matching each beat's distinctive
        # word only AT/AFTER the previous beat's time (monotonic), which stops an early "mothers" from
        # stealing a later beat. Enforces a >=1.5s slot per shot.
        MINSLOT=1.5
        def _find_time(vo, after):
            # Anchor on the beat's OPENING words, in order. Searching the longest word anywhere in the
            # beat (old behaviour) pinned ep09's sugar beat to "Mississippi", 17s into a 33-word line,
            # so the previous shot overstayed and the cut landed mid-beat. First-words-first fixes that;
            # the longest-word search is only a fallback when whisper mangled the opening.
            toks=[w for w in re.findall(r"[a-z0-9']+", vo.lower()) if len(w)>3]
            def _hit(tok):
                for x in WORDS:
                    if x['s']<after-0.01: continue
                    if x['w']==tok or (len(tok)>=6 and x['w'].startswith(tok[:6])): return x['s']
                return None
            for tok in toks[:4]:                                    # opening words, in spoken order
                t=_hit(tok)
                if t is not None and t < after+12.0: return t      # >12s ahead = a later occurrence, skip
            for tok in sorted(toks, key=len, reverse=True)[:8]:     # fallback: rarest/longest word
                t=_hit(tok)
                if t is not None: return t
            return None
        # POSITION-BASED (preferred): the body beats concatenated ARE the body reads, so beat i starts at
        # the aligned time of its first token, found by TOKEN INDEX. Immune to repeated words and long
        # lines (the word-anchor search stretched ep02's lemon crate to 20s and ep04's machine to 12s).
        btoks=[len(re.findall(r"[A-Za-z0-9']+", vo)) for vo in BEAT_VO[ep]]
        bodyidx=[i for i,k in enumerate(gkey) if k not in ('hook','closer')]
        if good_align and bodyidx and sum(btoks)==len(bodyidx):
            tstarts=[]; pos=0
            for n in btoks:
                tstarts.append(gtime[bodyidx[pos]]); pos+=n
            print(f'{ep}: beat times by token position: {[round(t,2) for t in tstarts]}')
        else:
            print(f'{ep}: token-position mismatch (beats {sum(btoks)} vs body reads {len(bodyidx)}) - word-anchor fallback')
            tstarts=[]; cursor=starts[body[0]]
            for vo in BEAT_VO[ep]:
                t=_find_time(vo, cursor)
                if t is None: t=cursor+0.8
                t=max(t, cursor); tstarts.append(t); cursor=t+0.3
        for i in range(len(tstarts)):                              # clamp: keep >=1.5s per remaining shot
            tstarts[i]=min(tstarts[i], cl_start-MINSLOT*(len(tstarts)-i))
            if i>0: tstarts[i]=max(tstarts[i], tstarts[i-1]+MINSLOT)
        c1=max(starts[body[0]]+0.10, tstarts[0])                   # opener holds until the first body line
        bounds=[tstarts[i+1] for i in range(len(shots)-1)]+[cl_start]
    else:
        span=cl_start-c1
        # MIN SHOT DURATION 1.5s: never let a shot flash. If the Director handed more clips than the
        # body span can hold at >=1.5s each, drop the extra middle clips (always keep the last/verdict
        # clip) so every remaining shot gets a real hold instead of a sub-second stutter.
        if len(shots)>1 and span/len(shots) < 1.5:
            keep=max(1, int(span//1.5))
            if keep < len(shots):
                shots = (shots[:keep-1]+[shots[-1]]) if keep>=2 else [shots[-1]]
        per=span/len(shots)
        bounds=[c1+per*(i+1) for i in range(len(shots)-1)]+[cl_start]
    T='(in/24)'
    # rise/walk clips carry their own camera motion, so they get gentler digital zoom than the static orb wide
    OPEN={'orb':(None,f'min(1.0+0.16*{T},1.80)',0.42,0.44),
          'rise':(f'{BATCH}/broll/b113.mp4',f'min(1.0+0.12*{T},1.45)',0.50,0.45),
          'walk':(f'{BATCH}/broll/b114.mp4',f'min(1.0+0.11*{T},1.42)',0.50,0.50)}
    if ep in OPENER_SRC: osrc,ozx,otx,oty=OPENER_SRC[ep]        # Director's hook clip
    else: osrc,ozx,otx,oty=OPEN[OPENER.get(ep,'orb')]
    # OWNER'S HOOK LENGTH WINS. By default the opener holds until the first body line (c1), which makes
    # the spoken hook decide where the visual hook cuts: a pair shorter than the read gets slowed to fill
    # the slot, a longer one gets trimmed past the owner's out-point. When the wrapper registered the
    # pair's own length, end the opener THERE and let the first body clip start under the tail of the
    # hook read. The hook card still holds for the whole spoken hook (it is timed off c1, not off this).
    o_end=c1
    if ep in OPENER_LEN:
        o_end=max(0.5, min(float(OPENER_LEN[ep]), (bounds[0] if bounds else cl_start)-1.5))
        _tail=('body starts under the tail of the hook read' if o_end<c1-0.05 else
               'the hook read ends first and the pair carries into the story line' if o_end>c1+0.05 else
               'pair and hook read end together')
        print(f'{ep}: opener = owner hook pair, {o_end/1.1:.2f}s on screen; '
              f'hook read runs to {c1/1.1:.2f}s - {_tail}')
    segs=[('opener',0,o_end,ozx,otx,oty,osrc)]
    prev=o_end; used={}
    for i,(name) in enumerate(shots):
        end=bounds[i]; dur=end-prev
        if name in DIRECTOR_CLIPS: srcp=DIRECTOR_CLIPS[name]; sd=dur_of(srcp); tx,ty=0.5,0.5   # Director's chosen clip
        elif name in LIB: srcp=f'{EP1A}/{name}.mp4'; sd,tx,ty=LIB[name]
        else: srcp=f'{BATCH}/broll/{BROLL[name]}.mp4'; sd=dur_of(srcp); tx,ty=0.5,0.52
        vst=0.0
        if used.get(name): vst=min(used[name], max(0.0,sd-1.0))
        if i%3==2: zx=f'max(1.20-0.04*{T},1.0)'
        else: zx=f'min({1.0 if not used.get(name) else 1.06}+0.04*{T},1.35)'
        segs.append((name,vst,end,zx,tx,ty,srcp))
        used[name]=used.get(name,0)+dur*0.8
        prev=end
    _clsrc=CLOSER_SRC.get(ep)   # Director's closer clip (the_peptide_vial) if provided, else orb
    segs.append(('closer',0,c_end,f'min(1.10+0.035*{T},1.45)',0.5 if _clsrc else 0.42,0.5 if _clsrc else 0.44, _clsrc))
    # derive sped motion clips
    dfiles=[]; acc=0.0; planpos=0.0; prev_end=0.0
    for i,(name,vst,end,zx,tx,ty,srcp) in enumerate(segs,1):
        pre_dur=end-prev_end; prev_end=end
        want=round(pre_dur/1.1,3)
        planpos+=want; want=max(0.3, round(planpos-acc,3))
        src=srcp or f'{EP1A}/lib_wide_purple_orb.mp4'
        # NEVER LOOP a source to fill a slot (looping is the "same clip wedged together" defect Gemini
        # caught on d_05). Pick a slowdown so ONE pass of the source exactly fills the slot; no
        # -stream_loop below means a slot longer than the source is filled by slowing, not repeating.
        sd=dur_of(src); need=max(0.3,pre_dur); sl=round(max(0.05,min(1.0,(sd-vst)/need)),3)
        if sl<0.75 and 1<i<len(segs):
            # Heavily slowed body clip (its own motion nearly stops at <0.75x): run ONE continuous soft
            # zoom across the WHOLE slot, paced to reach the cap exactly at the cut, so the frame is
            # never still (Gemini read the 0.5x anatomy/portrait/crate slots as freeze-frames).
            r=round(0.33/max(1.0,want),4)
            zx=f'max(1.34-{r}*{T},1.0)' if (i%3==0) else f'min(1.0+{r}*{T},1.34)'
        vf='scale=1440:2560:force_original_aspect_ratio=increase,crop=1440:2560'  # 1080 output; lighter intermediate = ~2x faster derive for the parallel batch
        if sl<1.0: vf+=f',setpts=PTS/{sl}'
        vf+=f',setpts=PTS/1.1,fps=24,zoompan=z=\'{zx}\':x=\'{tx}*iw*(1-1/zoom)\':y=\'{ty}*ih*(1-1/zoom)\':d=1:s=1080x1920:fps=24'
        if i==len(segs): vf+=f',fade=t=out:st={round(want-0.18,2)}:d=0.18'
        out=str(A/f'd_{i:02d}.mp4')
        cmd=['ffmpeg','-y','-loglevel','error']
        if vst: cmd+=['-ss',str(round(vst,3))]
        cmd+=['-i',src,'-vf',vf,'-t',str(want),'-an','-c:v','libx264','-preset','ultrafast','-crf','19','-pix_fmt','yuv420p','-r','24',out]
        run(cmd); got=dur_of(out); acc+=got; dfiles.append(out)
    # 4. captions ASS — FULL spoken text on screen (everything she says as read-along captions).
    #    Text comes from the KNOWN script (correct spelling of 'Semmelweis', 'childbed fever', etc.),
    #    timed by aligning the script tokens to the single whisper word pass. Hook words live in the
    #    top hook card, so lower-third captions begin after the hook (skip tokens spoken before c1).
    def ts(x):
        x=max(0.0,x/1.1); h=int(x//3600); m=int((x%3600)//60); s=x%60
        return f"{h}:{m:02d}:{s:05.2f}"
    if good_align:                                     # good alignment: correct script text, whisper times
        toks=[(gt[i].upper(), gtime[i], gend[i]) for i in range(len(gt))]
        brks=list(gbrk)                                 # break after a token that ended in punctuation
        tkey=list(gkey)                                 # which read (section) each token belongs to
    else:                                              # fallback: whisper's own tokens/timing
        toks=[(x['w'].upper(), x['s'], x['e']) for x in WORDS]
        brks=[False]*len(toks); tkey=[None]*len(toks)
    # chunk into natural read-along lines: break at punctuation / real pauses, ~3-6 words per line
    chunks=[]; cur=[]; curlen=0
    for i,(w,s,e_) in enumerate(toks):
        if not w or s<c1: continue                      # skip hook (shown in top card)
        cur.append((w,s,e_)); curlen+=len(w)+(1 if len(cur)>1 else 0)
        gap=(toks[i+1][1]-s) if i+1<len(toks) else 9.0
        hard=curlen>=30 or len(cur)>=6                  # never let a line run too long
        soft=curlen>=8 and (brks[i] or gap>0.6)         # prefer a sentence/comma or a real pause
        # a sentence end followed by a real pause, or the end of a read section (a hum sits there),
        # always closes the line - never carry "TIME" into "THE CURE WAS REAL" across the hum
        sec_end=(i+1<len(toks) and tkey[i+1]!=tkey[i]) or (brks[i] and gap>0.9)
        if hard or soft or sec_end:
            chunks.append(cur); cur=[]; curlen=0
    if cur: chunks.append(cur)
    folded=[]                                           # fold tiny filler orphans (a/of/at/the) onto prev line
    for c in chunks:
        if folded and len(c)==1 and len(c[0][0])<=3: folded[-1]=folded[-1]+c
        else: folded.append(c)
    chunks=folded
    evc=[[c[0][1], c[-1][2], ' '.join(w for w,*_ in c)] for c in chunks]   # end = last word's END time
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 1080","PlayResY: 1920","ScaledBorderAndShadow: yes","",
     "[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, BorderStyle, SecondaryColour, ScaleX, ScaleY, Spacing, Angle, Encoding",
     "Style: Default,Lilita One,58,&H00FFFFFF,&HE6000000,&H00000000,0,7,0,8,0,0,0,1,&H00FFFFFF,100,100,0,0,1","","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i,(s,we,txt) in enumerate(evc):
        e=we+0.30; e=max(e, s+0.6)                      # hold a beat past the last word's END...
        if i+1<len(evc): e=min(e, evc[i+1][0]-0.02)     # ...but never overlap the next line
        else: e=min(max(e, we+0.8), c_end-0.05)         # last line ("darling") holds until the picture fades
        # simple read-along caption: white, heavy black outline, quick fade (no bounce on every line)
        ov=rf"{{\an8\pos(540,1400)\fad(110,90)\fnLilita One\fs60\c&HFFFFFF&\3c&H000000&\bord7\shad0}}"
        lines.append(f"Dialogue: 0,{ts(s)},{ts(e)},Default,,0,0,0,,{ov}{txt}")
    (A/'captions.ass').write_text('\n'.join(lines))
    # 5. hook card (Option C single box). Rendered through hook_card.CardRenderer so an emoji in the
    #    headline draws as an emoji: the card font carries no emoji glyphs, and Noto Color Emoji is a
    #    bitmap font PIL will only open at one size, so emoji are cut out, drawn separately and pasted.
    from hook_card import CardRenderer
    _cr=CardRenderer(FP,62)
    card,bw,bh=_cr.render(HOOKS[ep])
    card.save(A/'hook_card.png')
    # COMPOSITION-AWARE PLACEMENT: the card's top edge comes from the opener's face/orb-free band
    # (HOOK_Y, set by the wrapper from opener_layout.json). Captions only start after the hook, so the
    # card may sit low (e.g. under the orb on the wides); clamped to the frame's safe margins.
    hy=int(HOOK_Y.get(ep, 300)); hy=max(80, min(hy, 1920-bh-60))
    print(f'{ep}: hook card at y={hy} (card {bw}x{bh})')
    # 6. compose via OpenMontage video_compose + overlay
    from tools.video.video_compose import VideoCompose
    vc=VideoCompose()
    cuts=[{"id":f"s{i:02d}","source":f,"in_seconds":0.0,"out_seconds":round(dur_of(f),3),"speed":1.0,"layer":"primary","reason":"derived motion clip"} for i,f in enumerate(dfiles,1)]
    edd={"version":"1.0","render_runtime":"ffmpeg","renderer_family":"documentary-montage","cuts":cuts,
      "overlays":[{"asset_id":"hook_card","start_seconds":0.0,"end_seconds":round(c1/1.1,2),"position":{"x":0,"y":hy},"opacity":1.0}],
      "metadata":{"compose_target":{"width":1080,"height":1920,"fit":"cover"},"hook_text":HOOKS[ep]}}
    validate('edit_decisions',edd); json.dump(edd,open(ART/'edit_decisions.json','w'),indent=1)
    # Restart-resilience: video_compose is the ~6min heavy step. If a complete base.mp4 already exists
    # (a prior attempt was killed AFTER compose but before overlay/mix finished), reuse it instead of
    # recomputing. Guarded by a duration check so a truncated/partial base.mp4 still triggers a rebuild.
    _bp=REN/'base.mp4'; _reuse=False
    if _bp.exists() and _bp.stat().st_size>1_000_000:
        try: _reuse = abs(dur_of(str(_bp)) - total) < 1.5
        except Exception: _reuse=False
    if _reuse:
        print(f'{ep}: reusing existing base.mp4 (dur ok) - skipping compose')
    else:
        res=vc.execute({"operation":"compose","edit_decisions":edd,"audio_path":str(A/'vo_final.wav'),
          "subtitle_path":str(A/'captions.ass'),"output_path":str(REN/'base.mp4'),"crf":21,"preset":"ultrafast"})
        assert res.success, res.error
    res2=vc.execute({"operation":"overlay","input_path":str(REN/'base.mp4'),
      "overlays":[{"asset_path":str(A/'hook_card.png'),"x":0,"y":hy,"start_seconds":0,"end_seconds":round(c1/1.1,2)}],
      "output_path":str(REN/f'{ep}_{slug}.mp4'),"crf":19})
    assert res2.success, res2.error
    final=str(REN/f'{ep}_{slug}.mp4'); fdur=dur_of(final)
    # 7. artifacts + checkpoints (batch pre-authorized by user)
    scr=validate('script',{"version":"1.0","title":SPEC[ep]['title'],"total_duration_seconds":round(total,2),
      "sections":[{"id":k,"text":reads[k],"start_seconds":round(starts.get(k,0),2),"end_seconds":round(starts.get(k,0)+D[k],2)} for k in keys],
      "metadata":{"approved":"user approved corrected scripts 2026-08-30"}})
    json.dump(scr,open(ART/'script.json','w'),indent=1)
    rr={"version":"1.0","outputs":[{"path":f'renders/{ep}_{slug}.mp4',"format":"mp4","codec":"h264","audio_codec":"aac","resolution":"1080x1920","fps":30,"duration_seconds":round(fdur,2),"platform_target":"tiktok"}],
      "verification_notes":["composed by video_compose (compose+overlay ops)","captions word-timed via whisper","hook card from hooks.json (user-editable)","round-2 hook fixes: VO at 0.32s, hook fade-in 0.15s, no opening hum, faster opener zoom, caption trigger alternates, fs74 captions"],
      "metadata":{"batch":"cleora-10","approval":"user pre-authorized full batch 2026-08-30 - 'Do not run confirm with me the steps'"}}
    validate('render_report',rr); json.dump(rr,open(ART/'render_report.json','w'),indent=1)
    brief=validate('brief',{"version":"1.0","title":SPEC[ep]['title'],"hook":reads['hook'],
      "key_points":[reads[k][:180] for k in keys if k not in ('hook','closer')][:3],
      "tone":"deadpan mystical storyteller","style":"claymation, soft zooms only","target_platform":"tiktok",
      "target_duration_seconds":round(total/1.1,1),"metadata":{"hook_text":HOOKS[ep],"batch":"cleora-10"}})
    json.dump(brief,open(ART/'brief.json','w'),indent=1)
    spn=validate('scene_plan',{"version":"1.0","scenes":[{"id":c["id"],"type":"broll","description":c["reason"],"start_seconds":0.0,"end_seconds":c["out_seconds"]} for c in cuts]})
    json.dump(spn,open(ART/'scene_plan.json','w'),indent=1)
    am=validate('asset_manifest',{"version":"1.0","assets":[{"id":f"d{i:02d}","type":"video","path":f,"source_tool":"project_motion_renderer","scene_id":f"s{i:02d}"} for i,f in enumerate(dfiles,1)]+[{"id":"vo","type":"audio","path":"assets/vo_final.wav","source_tool":"higgsfield_seed_audio_clone","scene_id":"narration"},{"id":"hook_card","type":"image","path":"assets/hook_card.png","source_tool":"pillow_derived","scene_id":"s01"}]})
    json.dump(am,open(ART/'asset_manifest.json','w'),indent=1)
    for st,art in [('idea',{'brief':brief}),('script',{'script':scr}),('scene_plan',{'scene_plan':spn}),('assets',{'asset_manifest':am}),('edit',{'edit_decisions':edd})]:
        write_checkpoint(PROJECTS_DIR,PID,st,'completed',art,pipeline_type='hybrid',human_approval_required=True,human_approved=True,metadata={"note":"batch pre-authorized by user ('run the 10 builds')"})
    write_checkpoint(PROJECTS_DIR,PID,'compose','completed',{'render_report':rr},pipeline_type='hybrid')
    print(f'  {ep} DONE: {round(fdur,1)}s -> {final}')
    return final

if __name__=='__main__':
    fails=[]
    for ep in sys.argv[1:]:
        print(f'=== building {ep} ===')
        try: build(ep)
        except Exception as e:
            print(f'  {ep} FAILED: {e}'); fails.append(ep)
    print('FAILED EPS:', fails or 'none')
