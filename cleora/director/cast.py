"""Cast an episode's clips locally, through OpenRouter, in parallel.

This is a faithful port of the three n8n nodes that make up [Cleora] Director
(ILloovicJh9HTH5v): Prep Inputs -> Assign Clips -> Build EDL + No-Repeat Guard.
The system prompt is the same file the workflow carries (system_prompt.txt,
vendored beside this script); the guard below is line-for-line the same rules.

Why a second copy exists: the workflow's Anthropic credential ran out of credit
mid-slate, and it casts one episode per execution. This runs the whole backlog
concurrently off the owner's OpenRouter key, so a 19-episode re-cast is one pass
instead of nineteen.

  OPENROUTER_API_KEY=... python3 cast.py ep521 ep522 ...   # named episodes
  OPENROUTER_API_KEY=... python3 cast.py --stale           # every stale one
  ... --dry                                                 # cast, do not write

Staleness is measured the only way that matters downstream: an EDL whose cut
count no longer matches its script's beat count was cast against an older script
and would put the wrong clip on every line after the divergence.
"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CA = '/root/.ccr/ca-bundle.crt'
SB = 'https://qlcmgxgwpzmiebzxflai.supabase.co/rest/v1'
SB_KEY = os.environ.get('SUPABASE_KEY','')
MODEL = 'anthropic/claude-sonnet-4.6'
MUSIC = ['owner_song_01.mp3', 'owner_song_02.mp3', 'owner_song_03.mp3']
MUSIC_BEDS = json.dumps([
    {"file": "owner_song_01.mp3", "feel": "short, sparse, brighter and lighter; suits a quick, wry, hopeful story"},
    {"file": "owner_song_02.mp3", "feel": "long, slow, dark and low; suits a heavy burial, betrayal or money story"},
    {"file": "owner_song_03.mp3", "feel": "long, slow, fuller and warmer; suits a discovery, recovery or wonder story"},
])
FALLBACK_SHOT = 'cleora_orb_open_dramatic'
CLOSER_SHOT = 'the_peptide_vial'


def _curl(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'curl failed: {r.stderr[:300]}')
    return r.stdout


def sb_get(path):
    return json.loads(_curl(['curl', '-sS', '--cacert', CA, f'{SB}/{path}',
                             '-H', f'apikey: {SB_KEY}', '-H', f'Authorization: Bearer {SB_KEY}']))


def sb_patch(path, body):
    return _curl(['curl', '-sS', '-X', 'PATCH', '--cacert', CA, f'{SB}/{path}',
                  '-H', f'apikey: {SB_KEY}', '-H', f'Authorization: Bearer {SB_KEY}',
                  '-H', 'Content-Type: application/json', '-H', 'Prefer: return=minimal',
                  '-d', json.dumps(body)])


# ---------------------------------------------------------------- Prep Inputs
def prep(row, lib, hooks):
    lib_slim = [{'shot_key': c['shot_key'], 'beat_role': c.get('beat_role'), 'mood': c.get('mood'),
                 'vo_safe': c.get('vo_safe'), 'talk_capable': c.get('talk_capable'),
                 'can_open': c.get('can_open') is True,
                 'subject_gender': c.get('subject_gender') or 'neutral',
                 'secs': float(c.get('duration_seconds') or 5), 'action': c.get('action') or ''}
                for c in lib]
    url_map = {c['shot_key']: c.get('video_public_url') for c in lib}
    sec_map = {c['shot_key']: float(c.get('duration_seconds') or 5) for c in lib}
    hooks_slim = [{'hook_key': h['hook_key'], 'name': h.get('name'),
                   'opens_on': h.get('shot_a_desc') or '', 'cuts_to': h.get('shot_b_desc') or '',
                   'cut_reads_as': h.get('cut_reads_as') or '', 'arc': h.get('emotional_arc') or '',
                   'energy': h.get('energy') or '', 'subject_of_second_shot': h.get('subject_of_b') or '',
                   'fits_stories_about': h.get('fits_stories_about') or [],
                   'avoid_for_stories_about': h.get('avoid_for_stories_about') or [],
                   'owner_note': h.get('owner_note') or ''} for h in hooks]
    beats = ((row.get('script') or {}).get('beats')) or []
    # `i` rides along so the model can echo it back and the guard can place each clip on the beat it
    # was chosen for, instead of trusting list order.
    beats_slim = [{'i': i, 'slot': b.get('slot'), 'vo': b.get('vo') or '', 'caption': b.get('caption') or ''}
                  for i, b in enumerate(beats)]
    return {'id': row['id'], 'content_id': row.get('content_id') or '', 'title': row.get('title') or '',
            'beats_json': json.dumps(beats_slim), 'library_json': json.dumps(lib_slim),
            'hooks_json': json.dumps(hooks_slim), 'full_beats': beats, 'lib_slim': lib_slim,
            'url_map': url_map, 'sec_map': sec_map, 'hook_map': {h['hook_key']: h for h in hooks}}


# --------------------------------------------------------------- Assign Clips
def ask(p, system, tries=4):
    user = (f"Episode: {p['title']}\nBEATS (assign one clip to EACH, keep order):\n{p['beats_json']}\n\n"
            f"SHOT LIBRARY (JSON):\n{p['library_json']}\n\n"
            f"HOOK OPENERS available (pick ONE hook_key, or \"none\"):\n{p['hooks_json']}\n\n"
            f"MUSIC BEDS (pick exactly one filename for the whole episode):\n{MUSIC_BEDS}\n\n"
            "Output the JSON now.")
    body = {'model': MODEL, 'max_tokens': 4000,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
    last = ''
    for a in range(tries):
        try:
            out = _curl(['curl', '-sS', '--cacert', CA, 'https://openrouter.ai/api/v1/chat/completions',
                         '-H', f"Authorization: Bearer {os.environ['OPENROUTER_API_KEY']}",
                         '-H', 'Content-Type: application/json', '--max-time', '240',
                         '-d', json.dumps(body)])
            j = json.loads(out)
            if j.get('choices'):
                return j['choices'][0]['message']['content']
            last = json.dumps(j.get('error') or j)[:300]
        except Exception as e:                     # noqa: BLE001 - retry anything transient
            last = str(e)[:300]
        time.sleep(2 ** a)
    raise RuntimeError(f'OpenRouter gave no completion after {tries} tries: {last}')


def parse_json(txt):
    raw = re.sub(r',(\s*[}\]])', r'\1', str(txt or '').strip())
    depth, start, blocks = 0, -1, []
    for i, ch in enumerate(raw):
        if ch == '{':
            if not depth:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if not depth and start != -1:
                blocks.append(raw[start:i + 1])
                start = -1
    for b in reversed(blocks):
        try:
            v = json.loads(b)
            if isinstance(v, dict):
                return v
        except Exception:                          # noqa: BLE001 - keep walking outward
            pass
    return None


# ----------------------------------------------------------------- The guard
FAMILIES = {'ward': ['sick_ward', 'the_ward', 'maternity', 'hospital_bed'],
            'bedside': ['the_caregiver', 'patient_recovers', 'doctor_patient', 'the_healing', 'nurse_tending'],
            'book': ['ancient_book', 'ledger', 'buried_records', 'scroll', 'handbook'],
            'money': ['coins', 'money', 'price_tag', 'gold'],
            'basin': ['wash_basin', 'hands_wash', 'washing'],
            'portrait': ['portrait'],
            'suits': ['the_suits', 'council_dismiss', 'whisper_council'],
            'cleora': ['cleora_', 'wide_closed_eye', 'wide_purple_orb']}
CLEORA_KEYS = {'wide_closed_eye', 'wide_purple_orb'}


def fam(k):
    if not k:
        return None
    for f, pats in FAMILIES.items():
        if any(p in k for p in pats):
            return f
    return None


def is_cleora(k):
    return bool(k) and (k.startswith('cleora_') or k in CLEORA_KEYS)


def music_for(d, seed):
    if d and isinstance(d.get('music'), str) and d['music'].strip() in MUSIC:
        return d['music'].strip()
    h = 0
    for ch in str(seed or ''):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return MUSIC[h % len(MUSIC)]


def align_by_index(d, n):
    """Place each clip on the beat it was chosen for. Zipping positionally meant one dropped entry
    slid every clip a beat down the script with nothing detecting it."""
    if not d or not isinstance(d.get('beats'), list):
        return {'ok': False, 'why': 'model returned no beats array'}
    out, seen = [None] * n, set()
    has_idx = any(isinstance(b, dict) and isinstance(b.get('i'), int) and not isinstance(b.get('i'), bool)
                  for b in d['beats'])
    if not has_idx:
        if len(d['beats']) != n:
            return {'ok': False, 'why': f"no beat indexes and count {len(d['beats'])} != {n}"}
        return {'ok': True, 'assign': [(b or {}).get('clip_key') for b in d['beats']],
                'note': 'positional (model omitted indexes)'}
    for b in d['beats']:
        i = (b or {}).get('i')
        if not isinstance(i, int) or isinstance(i, bool):
            return {'ok': False, 'why': 'an entry is missing its index'}
        if i < 0 or i >= n:
            return {'ok': False, 'why': f'index {i} outside 0..{n - 1}'}
        if i in seen:
            return {'ok': False, 'why': f'index {i} appears twice'}
        seen.add(i)
        out[i] = b.get('clip_key')
    missing = [k for k in range(n) if k not in seen]
    if missing:
        return {'ok': False, 'why': 'no entry for beat(s) ' + ','.join(map(str, missing))}
    return {'ok': True, 'assign': out, 'note': ''}


def fallback_hook(url_map, sec_map, reason):
    return {'hook_key': None, 'shots': 1, 'shot_a': FALLBACK_SHOT, 'shot_a_url': url_map.get(FALLBACK_SHOT),
            'in_a': 0, 'cut_a': min(5, sec_map.get(FALLBACK_SHOT, 5)), 'shot_b': None, 'shot_b_url': None,
            'in_b': 0, 'cut_b': 0, 'transition': 'none', 'move_a': None, 'move_b': None,
            'hook_y': 70, 'reason': reason}


def resolve_hook(d, hook_map, url_map, sec_map, title):
    key = (d.get('hook_key') or '').strip() if isinstance(d, dict) else ''
    said = (d.get('hook_reason') or '').strip() if isinstance(d, dict) else ''
    if not key or key.lower() == 'none':
        return fallback_hook(url_map, sec_map, said or 'director picked none')
    h = hook_map.get(key)
    if not h:
        return fallback_hook(url_map, sec_map, 'unknown hook_key ' + key)
    t = str(title or '').lower()
    for a in (h.get('avoid_for_stories_about') or []):
        a = str(a or '').lower().strip()
        if a and a in t:
            return fallback_hook(url_map, sec_map, f'{key} rejected: episode matches its avoid list ({a})')
    if not url_map.get(h.get('shot_a')) or not url_map.get(h.get('shot_b')):
        return fallback_hook(url_map, sec_map, f'{key} rejected: a shot is missing from the library')
    return {'hook_key': h['hook_key'], 'name': h.get('name'), 'shots': 2,
            'shot_a': h['shot_a'], 'shot_a_url': url_map[h['shot_a']],
            'in_a': float(h.get('in_a') or 0), 'cut_a': float(h.get('cut_a') or 2.4),
            'shot_b': h['shot_b'], 'shot_b_url': url_map[h['shot_b']],
            'in_b': float(h.get('in_b') or 0), 'cut_b': float(h.get('cut_b') or 2.5),
            'transition': h.get('transition') or 'cut', 'move_a': h.get('move_a'), 'move_b': h.get('move_b'),
            'hook_y': float(h.get('hook_y') or 300), 'reason': said or 'director pick'}


def build_edl(p, text):
    beats, url_map, sec_map = p['full_beats'], p['url_map'], p['sec_map']
    lib = p['lib_slim']
    role_of = {c['shot_key']: c.get('beat_role') or '' for c in lib}
    gender_of = {c['shot_key']: c.get('subject_gender') or 'neutral' for c in lib}
    talk_pool = [c['shot_key'] for c in lib if c.get('talk_capable')]
    vo_pool = [c['shot_key'] for c in lib if c.get('vo_safe')]
    d = parse_json(text)
    music = music_for(d, p['content_id'] or p['id'])
    hook = resolve_hook(d or {}, p['hook_map'], url_map, sec_map, p['title'])
    al = align_by_index(d, len(beats))
    assign = al['assign'] if al['ok'] else [None] * len(beats)

    cuts, used_all, swaps, prev = [], set(), [], None
    # REUSE IS ALLOWED - only ADJACENCY is banned. used_all is a PREFERENCE (an unused clip wins a tie),
    # never a veto, so a clip that genuinely depicts the line is not swapped out for a worse one.
    for bi, beat in enumerate(beats):
        is_talk = beat.get('slot') != 'body'
        pool = talk_pool if is_talk else vo_pool
        key = assign[bi] or None
        ok = lambda k: bool(k) and bool(url_map.get(k)) and (not pool or k in pool)          # noqa: E731
        fresh = lambda k: k not in used_all                                                   # noqa: E731
        body_ok = lambda k: True   # Cleora is allowed on body beats now (R4 relaxed by owner)  # noqa: E731
        if not ok(key):
            key = (next((k for k in pool if k != prev and fresh(k) and body_ok(k)), None)
                   or next((k for k in pool if k != prev and body_ok(k)), None)
                   or next((k for k in pool if k != prev), None)
                   or (pool[0] if pool else None))
        if key and key == prev:
            alt = (next((k for k in pool if k != prev and fresh(k) and body_ok(k)), None)
                   or next((k for k in pool if k != prev and body_ok(k)), None)
                   or next((k for k in pool if k != prev), None))
            if alt:
                key = alt
        if (not is_talk) and key and (prev and fam(key) and fam(key) == fam(prev)):
            g, r = gender_of.get(key), role_of.get(key)
            base = [k for k in vo_pool
                    if k != prev and not is_cleora(k) and (not prev or fam(k) != fam(prev)) and url_map.get(k)]
            unused = [k for k in base if fresh(k)]
            cands = unused or base
            pick = (next((k for k in cands if role_of.get(k) == r and gender_of.get(k) in ('neutral', g)), None)
                    or next((k for k in cands if role_of.get(k) == r), None)
                    or next((k for k in cands if gender_of.get(k) == 'neutral'), None)
                    or (cands[0] if cands else None))
            if pick:
                swaps.append(f'{key}->{pick}')
                key = pick
        cuts.append({'slot': beat.get('slot'), 'clip_key': key,
                     'url': url_map.get(key) if key else None,
                     'secs': float(beat.get('secs') or sec_map.get(key, 5)),
                     'caption': beat.get('caption') or '', 'vo': beat.get('vo') or ''})
        if key:
            used_all.add(key)
            prev = key

    missing = [c['clip_key'] or '?' for c in cuts if not c['url']]
    adj = any(cuts[k]['clip_key'] and cuts[k]['clip_key'] == cuts[k - 1]['clip_key'] for k in range(1, len(cuts)))
    hook_note = f"hook {hook['hook_key']}" if hook['hook_key'] else f"hook fallback: {hook['reason']}"
    bad = ('beat alignment: ' + al['why'] if not al['ok']
           else 'unresolved clips: ' + ','.join(missing) if missing
           else 'adjacent repeat unresolved' if adj else '')
    note = bad or ' | '.join([hook_note] + ([al['note']] if al.get('note') else [])
                             + (['guard swapped: ' + ', '.join(swaps)] if swaps else []))
    return {'edl': {'cuts': cuts, 'music': music, 'hook': hook},
            'script_status': 'failed' if bad else 'scripted',
            'notes': note, 'scripted_at': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())}, bad


# ------------------------------------------------------------------- driver
def stale_ids(epmap):
    rows = sb_get('cleora_content?select=id,content_id,script,edl&content_id=in.(%s)' % ','.join(epmap))
    out = []
    for r in rows:
        n = len(((r.get('script') or {}).get('beats')) or [])
        c = len(((r.get('edl') or {}).get('cuts')) or [])
        if n and c != n:
            out.append(r['content_id'])
    return out


def main(argv):
    dry = '--dry' in argv
    args = [a for a in argv if not a.startswith('--')]
    epmap = json.load(open(os.path.join(HERE, '..', 'slate', 'epmap.json')))
    rev = {v: k for k, v in epmap.items()}
    if '--stale' in argv:
        want = stale_ids(epmap)
    else:
        want = [rev.get(a, a) for a in args]
    if not want:
        print('nothing to cast')
        return 0
    system = open(os.path.join(HERE, 'system_prompt.txt')).read()
    lib = sb_get('cleora_clips?select=shot_key,beat_role,mood,vo_safe,talk_capable,can_open,'
                 'subject_gender,duration_seconds,action,video_public_url&status=eq.active')
    hooks = sb_get('cleora_hooks?select=*&status=eq.active&order=hook_key.asc')
    rows = sb_get('cleora_content?select=id,content_id,story_key,title,hook_text,script'
                  '&content_id=in.(%s)' % ','.join(want))
    print(f'casting {len(rows)} episodes on {MODEL} ({len(lib)} clips, {len(hooks)} hooks)'
          + (' [dry run]' if dry else ''))

    def one(row):
        p = prep(row, lib, hooks)
        try:
            body, bad = build_edl(p, ask(p, system))
        except Exception as e:                      # noqa: BLE001 - one episode must not sink the batch
            return row['content_id'], 'ERROR', str(e)[:160]
        if not dry:
            sb_patch(f"cleora_content?id=eq.{row['id']}", body)
        return row['content_id'], ('FAILED' if bad else 'ok'), body['notes']

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(one, rows))
    for cid, st, note in sorted(res, key=lambda x: epmap.get(x[0], x[0])):
        print(f'  {epmap.get(cid, cid):>6} {cid:<12} {st:<7} {note[:110]}')
    bad = [r for r in res if r[1] != 'ok']
    print(f'{len(res) - len(bad)}/{len(res)} cast clean')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
