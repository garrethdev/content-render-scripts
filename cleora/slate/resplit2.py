"""Split every over-long body beat on the 40-episode slate so no shot holds past the QA ceiling.

resplit.py (the first pass) ran only over the batch-4 id list and only split at punctuation, so a
20-word single clause joined by "and" - "...repair skin and keep cells talking to each other" - had no
boundary to break on and survived. Those are exactly the beats the QA gate now blocks on R10.

This pass:
  * works off slate/epmap.json (the real approved 40), so batch-5 episodes are covered too;
  * splits at the sentence boundary, then a clause boundary (, ; : -), then a coordinating
    conjunction (and / but / then / so / yet / or / while / because / when), then, only if nothing
    else exists, a structural word (to / for / with / from / into / that / which / of) - always the
    candidate nearest the middle, always keeping >=5 words a side;
  * is recursive, targeting <=15 words (~5.5s) per body beat;
  * PRESERVES TOKEN ORDER AND COUNT - the concatenated body text is byte-identical, so the voice
    reads already generated stay valid. Splitting a beat only moves where one shot ends and the next
    begins; not one spoken word changes, so nothing is re-voiced.

  python3 slate/resplit2.py            # report
  python3 slate/resplit2.py --apply    # write script + set script_status='written' for re-cast
"""
import json, os, re, subprocess, sys

KEY = os.environ.get('SUPABASE_KEY','')
CA = '/root/.ccr/ca-bundle.crt'
URL = 'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1/cleora_content'
H = ['-H', f'apikey: {KEY}', '-H', f'Authorization: Bearer {KEY}', '-H', 'Content-Type: application/json']
HERE = os.path.dirname(os.path.abspath(__file__))
MAXW = 17                                   # 17 spoken words ~= 6.3s: only split beats that would fail the 6.5s R10 gate
BODY = {'body', 'verdict'}
CONJ = re.compile(r'^(and|but|then|so|yet|or|while|because|when|which|that)$', re.I)
STRUCT = re.compile(r'^(to|for|with|from|into|of|on|at|by|as|in|inside|across|over|through|after|before|under|within|around|against|beyond|until)$', re.I)

try:
    from tts_prep import spoken as _spoken
except Exception:
    _spoken = lambda s: s
def wc(s): return len(re.findall(r"[A-Za-z0-9']+", _spoken(s) if s else ''))     # spoken length, so numeric beats measure true
def wc_raw(s): return len(re.findall(r"[A-Za-z0-9']+", s or ''))
def cap(s): return ' '.join(w for w in re.findall(r"[A-Za-z0-9']+", s) if len(w) > 2)[:40].upper()

def _candidates(vo):
    """All token indices we may cut before, from strongest boundary to weakest, each as (rank, idx)."""
    toks = vo.split()
    n = len(toks)
    cand = []
    for i in range(1, n):
        prev = toks[i - 1]
        w = re.sub(r"[^A-Za-z']", '', toks[i])
        if re.search(r'[.!?]$', prev):        cand.append((0, i))   # sentence end
        elif re.search(r'[,;:]$', prev):       cand.append((1, i))   # clause punctuation
        elif re.match(r'^[-–—]$', toks[i]) or re.match(r'^[-–—]', toks[i]):
            cand.append((1, i))                                      # dash
        elif CONJ.match(w):                    cand.append((2, i))   # coordinating conjunction
        elif STRUCT.match(w):                  cand.append((3, i))   # structural word, last resort
    return toks, cand

def split_long(b):
    if b['slot'] not in BODY or wc(b['vo']) <= MAXW:
        return [b]
    toks, cand = _candidates(b['vo'])
    n = len(toks)
    # Each side must hold at least MINSIDE spoken words, not raw tokens: "She died in 1974" is 4 raw
    # tokens but 6 spoken words - a fine 2.2s shot, not a flash. Measuring the floor in raw tokens
    # wrongly refused to split date- and number-heavy beats, which are exactly the long ones. 4 spoken
    # words ~= 1.5s = the MIN_HOLD floor: the shortest hold that still reads as a held shot.
    MINSIDE = 4
    valid = [(rank, abs(i - n / 2), i) for rank, i in cand
             if wc(' '.join(toks[:i])) >= MINSIDE and wc(' '.join(toks[i:])) >= MINSIDE]
    if not valid:
        return [b]
    best_rank = min(r for r, _, _ in valid)               # strongest boundary class available
    i = min((d, i) for r, d, i in valid if r == best_rank)[1]   # nearest the middle within it
    a = ' '.join(toks[:i]); c = ' '.join(toks[i:])
    ka = {k: v for k, v in b.items() if k not in ('vo', 'caption')}
    return (split_long({**ka, 'vo': a, 'caption': b.get('caption') or cap(a)})
            + split_long({**ka, 'vo': c, 'caption': cap(c)}))

def main(argv):
    m = json.load(open(os.path.join(HERE, 'epmap.json')))
    ids = list(m)
    todo = []
    for cid in ids:
        r = json.loads(subprocess.run(
            ['curl', '-s', '--cacert', CA, f'{URL}?content_id=eq.{cid}&select=content_id,script'] + H,
            capture_output=True, text=True).stdout)[0]
        s = r['script']; beats = s['beats']
        new = [x for b in beats for x in split_long(b)]
        if len(new) == len(beats):
            continue
        old_txt = ' '.join(b['vo'] for b in beats); new_txt = ' '.join(b['vo'] for b in new)
        assert re.findall(r"[A-Za-z0-9']+", old_txt) == re.findall(r"[A-Za-z0-9']+", new_txt), cid
        todo.append((cid, beats, new, s))
        lo, ln = max(wc(b['vo']) for b in beats), max(wc(b['vo']) for b in new)
        print(f"  {m[cid]} {cid}: {len(beats)}->{len(new)} beats; longest {lo}w->{ln}w "
              f"({lo/2.7:.1f}s->{ln/2.7:.1f}s)")
    print(f'{len(todo)} of {len(ids)} episodes re-split')
    if '--apply' in argv:
        for cid, old, new, s in todo:
            s2 = dict(s); s2['beats'] = new; s2['words'] = sum(wc_raw(b['vo']) for b in new)
            s2['source'] = (s.get('source') or '') + f' + resplit2>{MAXW}w'
            body = json.dumps({'script': s2, 'script_status': 'written',
                               'notes': f'beats re-split at <={MAXW} spoken words so no shot holds past ~6s; re-cast'})
            p = subprocess.run(['curl', '-s', '--cacert', CA, '-X', 'PATCH',
                                f'{URL}?content_id=eq.{cid}'] + H + ['-H', 'Prefer: return=minimal', '-d', body],
                               capture_output=True, text=True)
            ok = 'ok' if not p.stdout.strip() else p.stdout[:120]
            print('  PATCH', m[cid], cid, ok, _fix_turn_at(cid, old, new))
    return 0


# The reads files (hook/story/turn/closer text + turn_at) live with the render pipeline, not the repo.
READS_DIR = '/home/user/calesthio/openmontage/projects/cleora-batch/slate/reads'


def _fix_turn_at(cid, old, new):
    """Keep the story/turn read boundary on the same word after a split.

    turn_at is a body-beat INDEX (build_new_episode slices story = body[:turn_at], turn = body[turn_at:]).
    The two read wavs were cut at a fixed WORD boundary; splitting a beat before it adds beats and slides
    that index. No split ever crosses the boundary (it sits between beats), so the word partition is
    unchanged. The reads file's existing story text IS that boundary (in spoken form), so relocate the
    index to the new beat where the same spoken-word count is reached, and rewrite story/turn text. The
    audio is untouched, so an already-voiced episode stays valid."""
    p = os.path.join(READS_DIR, f'{cid}.reads.json')
    if not os.path.exists(p):
        return 'no reads file'
    rd = json.load(open(p))
    target = wc(rd.get('reads', {}).get('story', ''))            # spoken tokens up to the boundary
    new_body = [b for b in new if b['slot'] in BODY]
    ot = rd.get('turn_at')
    acc, nt = 0, len(new_body)
    for k, b in enumerate(new_body):
        if acc >= target:
            nt = k
            break
        acc += wc(b['vo'])
    rd['turn_at'] = nt
    rd.setdefault('reads', {})
    rd['reads']['story'] = _spoken(' '.join(b['vo'] for b in new_body[:nt]))
    rd['reads']['turn'] = _spoken(' '.join(b['vo'] for b in new_body[nt:]))
    ok = wc(rd['reads']['story']) == target
    json.dump(rd, open(p, 'w'), indent=1, ensure_ascii=False)
    return f'turn_at {ot}->{nt}' + ('' if ok else ' MISMATCH')

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
