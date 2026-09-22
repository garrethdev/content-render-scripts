"""Rebuild the four long-form reads from the CURRENT script, for episodes not yet voiced.

The reads (hook / story / turn / closer) were assembled before drop_today.py cut the TODAY-and-peptides
section and before resplit.py broke long beats up. Firing the queued TTS as it stood would have voiced
the section the owner told us to remove. This regenerates the read text from the beats that actually
survive, and carries the writer's own story->turn split forward by finding, in the new beat list, the
beat the old turn read started on.

  python3 rebuild_reads.py            # report only
  python3 rebuild_reads.py --write    # rewrite reads/<cid>.reads.json and the queued job text
"""
import json, os, re, sys

B = '/home/user/calesthio/openmontage/projects/cleora-batch'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'director'))
from tts_prep import spoken            # noqa: E402
import cast                            # noqa: E402

BODY_SLOTS = {'body', 'verdict'}
KEYS = ('hook', 'story', 'turn', 'closer')
norm = lambda s: re.sub(r'[^a-z0-9 ]', '', (s or '').lower())          # noqa: E731


def turn_index(body, old_turn):
    """Where the writer's turn read began, relocated in the current beat list.

    Matched on the first six words of the old read, which survive both the cut and the re-split. Falls
    back to the midpoint only if that text is gone entirely - a story with no located turn still needs
    two reads, and half-way is the least wrong guess."""
    head = ' '.join(norm(old_turn).split()[:6])
    if head:
        for i, b in enumerate(body):
            if norm(b.get('vo')).startswith(head[:len(norm(b.get('vo')))]) and norm(b.get('vo')):
                if head.startswith(norm(b.get('vo'))[:20]):
                    return i
        for i, b in enumerate(body):
            if norm(b.get('vo'))[:20] and head.startswith(norm(b.get('vo'))[:20]):
                return i
    return max(1, len(body) // 2)


def build(cid, beats, old):
    hook = next((b for b in beats if b.get('slot') == 'hook'), None)
    closer = next((b for b in reversed(beats) if b.get('slot') == 'closer'), None)
    body = [b for b in beats if b.get('slot') in BODY_SLOTS]
    ti = turn_index(body, (old.get('reads') or {}).get('turn') or '')
    ti = min(max(ti, 1), len(body) - 1) if len(body) > 1 else len(body)
    reads = {'hook': spoken(hook.get('vo') if hook else ''),
             'story': spoken(' '.join(b.get('vo') or '' for b in body[:ti])),
             'turn': spoken(' '.join(b.get('vo') or '' for b in body[ti:])),
             'closer': spoken(closer.get('vo') if closer else '')}
    return {'content_id': cid, 'turn_at': ti, 'reads': reads}


def main(argv):
    write = '--write' in argv
    m = json.load(open(f'{B}/slate/epmap.json'))
    rev = {v: k for k, v in m.items()}
    jobs = json.load(open(f'{B}/slate/tts_jobs.json'))
    # only episodes with no voice yet - a rebuilt read for an already-voiced episode would silently
    # desynchronise its cached wavs from its script.
    unvoiced = [ep for ep in sorted(m.values())
                if not all(os.path.exists(f'{B}/audio/{ep}_{k}.wav') for k in KEYS)]
    cids = [rev[e] for e in unvoiced]
    rows = {r['content_id']: r for r in
            cast.sb_get('cleora_content?select=content_id,script&content_id=in.(%s)' % ','.join(cids))}
    changed = 0
    for ep in unvoiced:
        cid = rev[ep]
        p = f'{B}/slate/reads/{cid}.reads.json'
        old = json.load(open(p)) if os.path.exists(p) else {}
        new = build(cid, rows[cid]['script']['beats'], old)
        diff = [k for k in KEYS if norm((old.get('reads') or {}).get(k)) != norm(new['reads'][k])]
        wc = sum(len(new['reads'][k].split()) for k in KEYS)
        print(f"  {ep} {cid:<12} turn_at {old.get('turn_at')}->{new['turn_at']:<3} {wc:4}w  "
              f"changed: {','.join(diff) or 'nothing'}")
        if diff or old.get('turn_at') != new['turn_at']:
            changed += 1
        if write:
            json.dump(new, open(p, 'w'), indent=1, ensure_ascii=False)
            for x in jobs:
                if x['ep'] == ep and x['key'] in KEYS:
                    if x.get('url') or x.get('job_id'):
                        continue                     # already in flight: never rewrite under it
                    x['text'] = new['reads'][x['key']]
                    x['turn_at'] = new['turn_at']
    if write:
        json.dump(jobs, open(f'{B}/slate/tts_jobs.json', 'w'), indent=1, ensure_ascii=False)
    print(f'{len(unvoiced)} unvoiced episodes, {changed} needed rebuilding'
          + (' - written' if write else ' - dry run, pass --write'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
