"""Keep N renders running until every slate episode with all four reads is done.

Re-scans on each pass, so episodes become renderable as their TTS lands - no need to wait for the whole
batch. After each render the intermediates (assets/, renders/base.mp4) are deleted: 40 episodes at the
full 356 MB each would not fit the disk, and only the final mp4 is wanted.
"""
import json,os,subprocess,sys,time,shutil,glob
B='/home/user/calesthio/openmontage/projects/cleora-batch'
LOG=f'{B}/slate/logs'; os.makedirs(LOG,exist_ok=True)
N=int(os.environ.get('RENDER_JOBS','2'))
m=json.load(open(f'{B}/slate/epmap.json')); rev={v:k for k,v in m.items()}
def done(ep):
    return bool(glob.glob(f'/home/user/calesthio/openmontage/projects/cleora-{ep}-*/renders/{ep}_*.mp4'))
def tidy(ep):
    for d in glob.glob(f'/home/user/calesthio/openmontage/projects/cleora-{ep}-*'):
        shutil.rmtree(f'{d}/assets',ignore_errors=True)
        b=f'{d}/renders/base.mp4'
        if os.path.exists(b): os.remove(b)
run={}
while True:
    subprocess.run([sys.executable,f'{B}/slate/mktts.py'],capture_output=True,cwd=B)
    ready=sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{B}/slate/tts/*.json'))
    todo=[e for e in ready if e not in run and not done(e)]
    for ep,p in list(run.items()):
        if p.poll() is not None:
            ok = p.returncode==0 and done(ep)
            print(f"[{time.strftime('%H:%M:%S')}] {ep} {'OK' if ok else 'FAILED rc=%s'%p.returncode}",flush=True)
            if ok: tidy(ep)
            del run[ep]
    while todo and len(run)<N:
        ep=todo.pop(0)
        f=open(f'{LOG}/{ep}.log','w')
        run[ep]=subprocess.Popen([sys.executable,f'{B}/build_new_episode.py',ep,rev[ep],f'{B}/slate/tts/{ep}.json'],
                                 stdout=f,stderr=subprocess.STDOUT,cwd=B)
        print(f"[{time.strftime('%H:%M:%S')}] started {ep} ({rev[ep]})",flush=True)
    if not run and not todo:
        remaining=[e for e in m.values() if not done(e)]
        if not remaining: print('ALL RENDERED',flush=True); break
        print(f"[{time.strftime('%H:%M:%S')}] idle - waiting on TTS for {len(remaining)} eps",flush=True)
    time.sleep(20)
