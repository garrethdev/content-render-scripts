"""Lay a sound effect onto a fully rendered episode, on a real timeline.

The SFX is a track in the episode's edit_decisions.json (OpenMontage's timeline document) - not a
one-off ffmpeg command - so the placement is recorded, reviewable and re-runnable. Mixing goes through
OpenMontage's AudioMixer, the same tool that laid down her voice and the music bed.

  --source   the effect file (video or audio; the audio stream is what is used)
  --keep     fraction of the source to KEEP from the start (0.2 = chop the last 80%)
  --at       timeline seconds to fire it, repeatable
  --gain     dB relative to the episode mix (negative = under the voice)

Usage:
  python3 slate/sfx.py --ep ep503 --source /path/Ringtone.mp4 --keep 0.2 --at 0.0 --gain -8
"""
import argparse,glob,json,os,subprocess,sys
B='/home/user/calesthio/openmontage/projects/cleora-batch'
sys.path.insert(0,'/home/user/calesthio/openmontage')

def probe(p, stream='a'):
    r=subprocess.run(['ffprobe','-v','error','-select_streams',stream,'-show_entries',
                      'format=duration','-of','csv=p=0',p],capture_output=True,text=True,check=True)
    return float(r.stdout.strip())

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--ep',required=True); a.add_argument('--source',required=True)
    a.add_argument('--keep',type=float,default=0.2); a.add_argument('--gain',type=float,default=-8.0)
    a.add_argument('--seconds',type=float,default=None,
                   help='absolute clip length in seconds; overrides --keep')
    a.add_argument('--fade',type=float,default=0.08,
                   help='fade-out length in seconds, ending at the clip out-point')
    a.add_argument('--at',type=float,action='append',default=[])
    a.add_argument('--name',default=None)
    o=a.parse_args()
    if not os.path.exists(o.source): sys.exit(f'source not found: {o.source}')
    proj=glob.glob(f'/home/user/calesthio/openmontage/projects/cleora-{o.ep}-*')
    if not proj: sys.exit(f'no rendered project for {o.ep}')
    proj=proj[0]
    vid=sorted(glob.glob(f'{proj}/renders/{o.ep}_*.mp4'))
    vid=[v for v in vid if 'sfx' not in os.path.basename(v)]
    if not vid: sys.exit(f'no rendered video in {proj}/renders')
    vid=vid[0]
    name=o.name or os.path.splitext(os.path.basename(o.source))[0].lower()
    at=o.at or [0.0]

    # 1. TRIM. Keep the head of the source and drop the rest, fading out into the cut so the effect
    # LEAVES rather than stopping dead.
    full=probe(o.source)
    cut=round(o.seconds if o.seconds else full*o.keep, 3)
    fade=min(o.fade, cut)                    # a fade longer than the clip would start before it does
    os.makedirs(f'{B}/sfx',exist_ok=True)
    stub=f'{B}/sfx/{name}_{cut:g}s.wav'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-t',str(cut),'-i',o.source,'-vn',
                    '-ac','2','-ar','48000',
                    '-af','afade=t=out:st=%.3f:d=%.3f'%(max(0,cut-fade),fade),
                    stub],check=True)
    print(f'{name}: source {full:.2f}s -> kept first {cut:.2f}s, {fade:.2f}s fade out -> {stub}')

    # 2. TIMELINE. Episode mix as track 0, and ONE full-length SFX bed as track 1 - silence everywhere
    # except the hits. Both tracks must be the SAME LENGTH: amix divides by the input count and uses
    # dropout_transition to ramp the survivors back up when a short input ends, so a 6s effect over a
    # 56s episode would duck her voice by 6 dB for exactly as long as the effect plays - cancelling the
    # effect out. Equal lengths make that halving uniform, which the loudnorm stage then undoes.
    from tools.audio.audio_mixer import AudioMixer
    from tools.video.video_compose import VideoCompose
    mixer=AudioMixer()
    base=f'{B}/sfx/{o.ep}_base.wav'
    ex=mixer.execute({'operation':'extract','input_path':vid,'output_path':base})
    assert ex.success, f'AudioMixer extract failed: {ex.error}'
    epdur=probe(base)
    bed=f'{B}/sfx/{o.ep}_{name}_bed.wav'
    vol=10**(o.gain/20.0)
    ins=[]; chains=[]; labels=''
    for n,t in enumerate(at):
        ins += ['-i',stub]
        chains.append(f"[{n}:a]volume={vol:.4f},adelay={int(t*1000)}|{int(t*1000)}[s{n}]")
        labels += f'[s{n}]'
    mixhits = (f"{labels}amix=inputs={len(at)}:duration=longest:normalize=0[hits]"
               if len(at)>1 else f"{labels}anull[hits]")
    subprocess.run(['ffmpeg','-y','-loglevel','error']+ins+
                   ['-filter_complex',';'.join(chains+[mixhits,
                    f"[hits]apad=whole_dur={epdur:.3f},atrim=0:{epdur:.3f}[bed]"]),
                    '-map','[bed]','-ac','2','-ar','48000',bed],check=True)
    tracks=[{'path':base,'role':'speech','volume':1.0},
            {'path':bed,'role':'sfx','volume':1.0}]
    mixed=f'{B}/sfx/{o.ep}_mix.wav'
    res=mixer.execute({'operation':'mix','tracks':tracks,'normalize':True,
                       'loudnorm_target':-14,'output_path':mixed})
    assert res.success, f'AudioMixer mix failed: {res.error}'

    # 3. LAY IT BACK on the picture through OpenMontage's video_compose - the same tool that assembled
    # the episode - with the finished render as a single cut and the new mix as its audio track.
    out=f'{proj}/renders/{o.ep}_sfx.mp4'
    vdur=probe(vid,'v')
    edl_one={'version':'1.0','render_runtime':'ffmpeg','renderer_family':'documentary-montage',
      'cuts':[{'id':'s01','source':vid,'in_seconds':0.0,'out_seconds':round(vdur,3),'speed':1.0,
               'layer':'primary','reason':'finished episode, picture untouched'}],'overlays':[],
      'metadata':{'compose_target':{'width':1080,'height':1920,'fit':'cover'}}}
    cr=VideoCompose().execute({'operation':'compose','edit_decisions':edl_one,'audio_path':mixed,
                               'output_path':out,'crf':19,'preset':'veryfast'})
    assert cr.success, f'VideoCompose compose failed: {cr.error}'

    # 4. RECORD it on the timeline document so the placement is not lost in a shell command.
    ed=f'{proj}/artifacts/edit_decisions.json'
    if os.path.exists(ed):
        d=json.load(open(ed))
        d.setdefault('audio_tracks',[])
        d['audio_tracks']=[x for x in d['audio_tracks'] if x.get('id')!=f'sfx_{name}']
        d['audio_tracks'].append({'id':f'sfx_{name}','role':'sfx','source':stub,
            'source_original':os.path.abspath(o.source),'source_kept_fraction':o.keep,
            'clip_seconds':cut,'gain_db':o.gain,
            'hits':[{'start_seconds':round(t,3),'end_seconds':round(t+cut,3)} for t in at]})
        json.dump(d,open(ed,'w'),indent=1)
        print(f'timeline: wrote sfx_{name} into {ed}')
    print(f'{o.ep}: {len(at)} hit(s) at {at} @ {o.gain} dB -> {out}')

if __name__=='__main__': main()
