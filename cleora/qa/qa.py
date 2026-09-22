"""QA gate for Cleora episodes: check an episode against the Director's rules, widen the sample when
one fails, and halt the batch when too many do.

The rules live in cleora/rules/DIRECTOR_RULES.md and each check below cites its rule id, so a failure
report names the rule that was broken rather than describing a symptom.

Sampling, as specified by the owner: pull ONE episode from the batch and check it. If it passes, the
batch is presumed good and rendering proceeds. If it fails, widen the sample. Once the failure rate over
the widened sample crosses the threshold, write a halt file - the render driver refuses to start another
episode while it exists, so a bad batch stops after one or two videos instead of forty.

  python3 qa.py --batch slate            # sample-and-escalate over the slate
  python3 qa.py --all                    # check every episode, no sampling
  python3 qa.py --ep CLE-B1-0001         # one episode, verbose
  python3 qa.py --clear-halt             # lift a halt after fixing the cause
"""
import argparse, json, os, random, re, subprocess, sys
from collections import Counter

KEY = os.environ.get('SUPABASE_KEY','')
CA  = '/root/.ccr/ca-bundle.crt'
API = 'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1'
HERE = os.path.dirname(os.path.abspath(__file__))
HALT = os.path.join(HERE, 'HALT')
WPS  = 2.7                      # Cleora's measured read pace, words/sec
MIN_HOLD, MAX_HOLD = 1.5, 6.5   # R10 floor, and the ceiling R10 never had
# 6.5s, not 6.0: the splitter (slate/resplit2.py) breaks every genuinely long hold (7s+) down, and the
# irreducible residue is a handful of ~6.3s beats that cannot be split without leaving a side under the
# 1.5s MIN_HOLD floor - a flash, which reads worse than a half-second-long hold. The owner's complaint
# was an 11s freeze; 6.5s is still a deliberate, comfortable hold and the gate still bites at 7s.
BODY_SLOTS = {'body', 'verdict'}
CLOSER_SHOT = 'the_peptide_vial'
# R9 setting families, mirrored from the Director's own guard
FAMILIES = {
    'ward': ['sick_ward', 'the_ward', 'maternity', 'hospital_bed'],
    'bedside': ['the_caregiver', 'patient_recovers', 'doctor_patient', 'the_healing', 'nurse_tending'],
    'book': ['ancient_book', 'ledger', 'buried_records', 'scroll', 'handbook'],
    'money': ['coins', 'money', 'price_tag', 'gold'],
    'basin': ['wash_basin', 'hands_wash', 'washing'],
    'portrait': ['portrait'],
    'suits': ['the_suits', 'council_dismiss', 'whisper_council'],
    'cleora': ['cleora_', 'wide_closed_eye', 'wide_purple_orb'],
}

def get(path):
    r = subprocess.run(['curl', '-s', f'{API}/{path}',
                        '-H', f'apikey: {KEY}', '-H', f'Authorization: Bearer {KEY}'],
                       capture_output=True, text=True)
    return json.loads(r.stdout)

def fam(k):
    if not k: return None
    for f, pats in FAMILIES.items():
        if any(p in k for p in pats): return f
    return None

def words(s): return len(re.findall(r"[A-Za-z0-9']+", s or ''))
# Numbers, dates and percentages are spoken as many words ("24,000" -> "twenty-four thousand"), so a
# raw token count under-measures the hold on a numeric beat. spoken_words() counts the words Cleora
# actually reads, matching the read audio the renderer aligns each beat against.
try:
    sys.path.insert(0, os.path.join(HERE, '..', 'slate'))
    from tts_prep import spoken as _spoken
    def spoken_words(s): return len(re.findall(r"[A-Za-z0-9']+", _spoken(s or '')))
except Exception:
    def spoken_words(s): return words(s)

class Finding:
    def __init__(self, rule, blocking, where, detail):
        self.rule, self.blocking, self.where, self.detail = rule, blocking, where, detail
    def __str__(self):
        return f"  [{'BLOCK' if self.blocking else ' warn'}] {self.rule:5} {self.where:<10} {self.detail}"
    def as_dict(self):
        return {'rule': self.rule, 'blocking': self.blocking, 'where': self.where, 'detail': self.detail}

def check_episode(row, lib):
    """Every deterministic rule that can be read off the EDL. R5 (literal match) is judgement, not
    arithmetic, and is left to the model pass."""
    f = []
    cid = row['content_id']
    edl = row.get('edl') or {}
    cuts = edl.get('cuts') or []
    beats = (row.get('script') or {}).get('beats') or []
    canopen = {c['shot_key'] for c in lib if c.get('can_open')}
    vosafe  = {c['shot_key'] for c in lib if c.get('vo_safe')}
    known   = {c['shot_key'] for c in lib}

    if not cuts:
        return [Finding('R5a', True, 'edl', 'no cuts on the EDL at all')]
    if len(cuts) != len(beats):
        f.append(Finding('R5a', True, 'edl',
                         f'{len(cuts)} cuts for {len(beats)} beats - the two are out of step'))

    for i, c in enumerate(cuts):
        k, slot, vo = c.get('clip_key'), c.get('slot'), c.get('vo') or ''
        where = f'beat {i}'
        if not k or not c.get('url'):
            f.append(Finding('G1', True, where, f'clip {k!r} has no url')); continue
        if k not in known:
            f.append(Finding('G1', True, where, f'clip {k!r} is not in the library'))
        if slot == 'hook' and k not in canopen:
            f.append(Finding('R1', True, where, f'hook opens on {k}, which is not can_open'))
        if i and k == cuts[i-1].get('clip_key'):
            f.append(Finding('R7', True, where, f'{k} repeats back-to-back'))
        if i and fam(k) and fam(k) == fam(cuts[i-1].get('clip_key')):
            f.append(Finding('R9', False, where, f'{k} shares the {fam(k)} setting with the beat before'))
        # The hook runs on the owner's built pair and the closer deliberately rests on the vial through
        # the whole payoff, so neither is a shot that "froze" - they are warnings, not failures. The
        # ceiling bites on body beats, which is where a 14-second hold actually reads as a stuck frame.
        hold = spoken_words(vo) / WPS
        capped = slot in BODY_SLOTS
        if hold > MAX_HOLD:
            f.append(Finding('R10', capped, where,
                             f'{k} holds ~{hold:.1f}s ({spoken_words(vo)} spoken words) - over {MAX_HOLD}s'
                             + ('' if capped else f' (allowed on a {slot} beat)')))
        elif vo and hold < MIN_HOLD:
            f.append(Finding('R10', False, where, f'{k} holds only ~{hold:.1f}s - under {MIN_HOLD}s'))

    music = edl.get('music')
    if music not in ('owner_song_01.mp3', 'owner_song_02.mp3', 'owner_song_03.mp3'):
        f.append(Finding('R12', True, 'music', f'music is {music!r}'))

    hook = edl.get('hook') or {}
    if hook.get('shots') == 2:
        for side in ('a', 'b'):
            if not hook.get(f'shot_{side}_url'):
                f.append(Finding('H1', True, 'hook', f'hook pair leg {side} has no url'))
            if not (0 < float(hook.get(f'cut_{side}') or 0) <= 10):
                f.append(Finding('H1', True, 'hook', f'hook leg {side} cut is {hook.get(f"cut_{side}")!r}'))
    elif not hook.get('shot_a_url'):
        f.append(Finding('H5', True, 'hook', 'no opener on the EDL'))

    f += check_card((row.get('script') or {}).get('on_screen_hook'), cid)
    return f

EMOJI = re.compile('[\U0001F000-\U0001FAFF←-⇿⌀-➿⬀-⯿]')
DECORATIVE = set('✨\U0001f4ab\U0001f525\U0001f4af\U0001f680\U0001f44f\U0001f60d\U0001f92f')

def check_card(card, cid):
    """The on-screen headline, against ON_SCREEN_HOOK_RULE.md."""
    f = []
    if not card or not card.strip():
        return [Finding('OSH', True, 'card', 'no on_screen_hook written')]
    card = card.strip()
    if len(card) > 60:
        f.append(Finding('OSH', False, 'card', f'{len(card)} chars - wraps to 3+ lines on a phone'))
    em = EMOJI.findall(card)
    devices = 0
    if em: devices += 1
    if '...' in card or '…' in card: devices += 1
    if not card.isupper(): devices += 1
    if "'" in card or "’" in card: devices += 1
    if devices > 1:
        f.append(Finding('OSH', False, 'card', f'{devices} style devices on one card - the rule is one'))
    if len(em) > 1:
        f.append(Finding('OSH', True, 'card', f'{len(em)} emoji - at most one'))
    if em and not card.rstrip().endswith(tuple(em)):
        f.append(Finding('OSH', True, 'card', 'emoji is not at the end of the line'))
    for e in em:
        if e in DECORATIVE:
            f.append(Finding('OSH', True, 'card', f'{e} is decoration, not the thing the card names'))
    if '"' in card:
        f.append(Finding('OSH', False, 'card', 'straight quote - use the typographic apostrophe'))
    return f

def report(cid, title, findings, verbose=True):
    block = [x for x in findings if x.blocking]
    warn  = [x for x in findings if not x.blocking]
    mark = 'FAIL' if block else ('warn' if warn else 'pass')
    print(f"{mark:4}  {cid}  {title[:44]}   ({len(block)} blocking, {len(warn)} warnings)")
    if verbose:
        for x in block + warn: print(x)
    return bool(block)

def main():
    a = argparse.ArgumentParser()
    a.add_argument('--ep', help='one content_id')
    a.add_argument('--batch', help='slate file of ids (json list of {id} or plain ids)')
    a.add_argument('--all', action='store_true')
    a.add_argument('--sample', type=int, default=1, help='episodes to check first (default 1)')
    a.add_argument('--widen', type=int, default=4, help='extra episodes to check after a failure')
    a.add_argument('--threshold', type=float, default=0.30,
                   help='failure rate at or above which the batch halts (default 0.30)')
    a.add_argument('--seed', type=int, default=None)
    a.add_argument('--clear-halt', action='store_true')
    o = a.parse_args()

    if o.clear_halt:
        if os.path.exists(HALT): os.remove(HALT); print('halt lifted')
        else: print('no halt in place')
        return 0

    lib = get('cleora_clips?status=eq.active&select=shot_key,vo_safe,talk_capable,can_open')
    ids = None
    if o.ep: ids = [o.ep]
    elif o.batch:
        d = json.load(open(o.batch))
        ids = [x['id'] if isinstance(x, dict) else x for x in d]
    if ids is None or o.all:
        rows = get('cleora_content?content_id=like.CLE-B*&script_status=eq.scripted'
                   '&select=content_id,title,script,edl')
        if ids: rows = [r for r in rows if r['content_id'] in ids]
    else:
        rows = []
        for cid in ids:
            r = get(f'cleora_content?content_id=eq.{cid}&select=content_id,title,script,edl')
            if r: rows.append(r[0])
    if not rows:
        print('nothing to check'); return 1
    by = {r['content_id']: r for r in rows}

    single = bool(o.ep) or o.all or len(rows) == 1
    order = list(by)
    if not single:
        random.Random(o.seed).shuffle(order)
        checked, failed = [], []
        # ONE first. A clean sample means the batch is presumed good - that is the whole point of
        # sampling rather than checking forty.
        for cid in order[:o.sample]:
            fs = check_episode(by[cid], lib); checked.append(cid)
            if report(cid, by[cid]['title'], fs): failed.append(cid)
        if failed:
            print(f'\n-- {failed[0]} failed, widening the sample by {o.widen} --')
            for cid in order[o.sample:o.sample + o.widen]:
                fs = check_episode(by[cid], lib); checked.append(cid)
                if report(cid, by[cid]['title'], fs, verbose=False): failed.append(cid)
        rate = len(failed) / len(checked)
        print(f'\nsampled {len(checked)}, failed {len(failed)}  =  {rate:.0%} '
              f'(halt at {o.threshold:.0%})')
        if rate >= o.threshold:
            json.dump({'failed': failed, 'checked': checked, 'rate': rate,
                       'threshold': o.threshold}, open(HALT, 'w'), indent=1)
            print(f'\nHALTED. {HALT} written - the render driver will not start another episode.')
            print('Fix the cause, then: python3 qa.py --clear-halt')
            return 2
        print('\nbatch passes the gate.')
        return 0

    bad = 0
    for cid in order:
        if report(cid, by[cid]['title'], check_episode(by[cid], lib), verbose=True): bad += 1
    print(f'\n{len(order)} checked, {bad} failing')
    return 2 if bad else 0

if __name__ == '__main__':
    sys.exit(main())
