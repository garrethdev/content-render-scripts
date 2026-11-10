"""Simulate the opener variety governor with your real hook + can_open data.
Worst case: history is 10x hook03 (today's reality) and the model picks hook03 for every new episode.
    python3 test_opener_governor.py
"""
from collections import Counter
import cast

CAN_OPEN = ['asmr_cauldron_stir', 'asmr_walk_to_cauldron', 'cleora_face', 'cleora_looking_into_orb',
            'cleora_orb_open_calm', 'cleora_orb_open_dramatic', 'cleora_orb_wide', 'cleora_tight',
            'cleora_walk', 'eyes_dilated_purple', 'eyes_dilated_zoom_reveal', 'wide_closed_eye']
HOOKS = {  # hook_key: (shot_a, shot_b, avoid list)
    'hook01': ('cleora_orb_open_dramatic', 'eyes_dilated_purple', ['modern scientific breakthroughs']),
    'hook02': ('cleora_orb_open_dramatic', 'female_doctor', ['modern cosmetic procedures']),
    'hook03': ('wide_closed_eye', 'cleora_orb_open_dramatic', ['modern clinical science']),
    'hook04': ('ancient_book_close', 'eyes_dilated_zoom_reveal', ['gentle natural healing']),
    'hook05': ('ancient_book_close', 'eyes_dilated_zoom_reveal', ['peaceful natural remedies']),
    'hook06': ('healer_brew_med', 'eyes_dilated_zoom_reveal', ['gentle natural remedies']),
    'hook07': ('healer_brew_med', 'eyes_dilated_purple', ['gentle natural remedies']),
}
shots = set(CAN_OPEN) | {x for a, b, _ in HOOKS.values() for x in (a, b)}
url_map = {k: f'https://x/{k}.mp4' for k in shots}
sec_map = {k: 6.0 for k in shots}
hook_map = {k: {'hook_key': k, 'name': k, 'shot_a': a, 'shot_b': b, 'avoid_for_stories_about': av}
            for k, (a, b, av) in HOOKS.items()}
lib_slim = [{'shot_key': k, 'can_open': k in CAN_OPEN} for k in shots]

def run(n=60, picked='hook03'):
    cast._OPENER_LOG[:] = ['wide_closed_eye'] * 10          # today: every recent video opened the same way
    out = []
    for i in range(n):
        p = {'title': f'episode {i}', 'content_id': f'ep{i}', 'hook_map': hook_map,
             'url_map': url_map, 'sec_map': sec_map, 'lib_slim': lib_slim}
        h = cast.govern_hook(cast.resolve_hook({'hook_key': picked}, hook_map, url_map, sec_map, p['title']), p)
        out.append(h['shot_a'])
    return out

out = run()
print('first frames chosen for 60 episodes, model always asking for hook03:')
for k, v in Counter(out).most_common():
    print(f'  {v:>3}  {k}')
worst = max(Counter(out[i:i + 10]).most_common(1)[0][1] for i in range(len(out) - 9))
back2back = sum(1 for a, b in zip(out, out[1:]) if a == b)
print(f'distinct first frames: {len(set(out))}   max in any 10-episode window: {worst}   back-to-back repeats: {back2back}')
assert worst <= cast.OPENER_MAX_IN_WINDOW and back2back == 0, 'governor failed'
print('PASS')

# look-alike families: no group may exceed the cap or repeat back to back
fams = [cast.fam(x) for x in out]
assert all(a != b for a, b in zip(fams, fams[1:])), 'look-alike opener repeated back to back'
assert all(Counter(fams[i:i + 10])[f] <= 2 for i in range(len(fams) - 9) for f in set(fams[i:i + 10])), 'family cap broken'
print('OK: look-alike families respect the cap and never repeat consecutively')
