"""Inspect encoded output format and create a review index and contact sheets."""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from render import ffmpeg_path, prepare_segment, validate

ROOT = Path(__file__).resolve().parent
bank = json.loads((ROOT / 'stories-50.json').read_text())
validate(bank)
assert len(bank) == 50
stories = {s['id']: s for s in bank}
plan = json.loads((ROOT / 'render-plan-20.json').read_text())
clips = {c['shot_key']: c for c in json.loads((ROOT / 'footage/clips.json').read_text())}
assert len(plan) == 20 and len({p['story_id'] for p in plan}) == 20
font = ImageFont.truetype(str(ROOT / 'fonts/TikTokSans-Semibold.ttf'), 19)
results, previews = [], []
review = ['# Madame Cleora — first 20 videos', '', 'Each output is eight seconds: one complete text screen from 0–4s, then another from 4–8s. Silent, ready for the next editing step.', '']

for p in plan:
    story_id = p['story_id']
    s = stories[story_id]
    file = ROOT / 'renders' / (story_id + '.mp4')
    cap = cv2.VideoCapture(str(file))
    rate = cap.get(cv2.CAP_PROP_FPS)
    count = round(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width, height = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    assert count == 240 and abs(rate - 30) < .001 and (width, height) == (1080, 1920), str(file)
    samples = {}
    for number in range(240):
        ok, frame = cap.read()
        assert ok, f'{story_id} could not decode frame {number}'
        if number not in [0, 30, 119, 120, 150, 239]:
            continue
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        samples[number] = image
        if number in [30, 150]:
            image.save(ROOT / 'renders' / story_id / f'preview-{1 if number == 30 else 2}.jpg')
    cap.release()
    differences = []
    for half, key in enumerate(['opener', 'closer']):
        segment = prepare_segment(clips[p[key]], p[key + '_start'], ROOT / 'renders/cache')
        source_capture = cv2.VideoCapture(str(segment))
        text_layer = Image.open(ROOT / 'renders' / story_id / f'screen-{half+1}.png').convert('RGBA')
        for number in range(120):
            ok, source_frame = source_capture.read()
            assert ok
            if number not in [0, 119]:
                continue
            expected = Image.alpha_composite(Image.fromarray(cv2.cvtColor(source_frame, cv2.COLOR_BGR2RGBA)), text_layer).convert('RGB')
            actual = samples[half * 120 + number]
            difference = float(np.abs(np.asarray(expected).astype(float) - np.asarray(actual).astype(float)).mean())
            differences.append(round(difference, 3))
            assert difference < 6, f'{story_id}: wrong text or footage at frame {half*120+number}: {difference}'
        source_capture.release()
    layouts = json.loads((ROOT / 'renders' / story_id / 'layout.json').read_text())
    assert len(layouts[0]['highlight_boxes']) == 2 and layouts[1]['highlight_boxes'] == [], story_id
    assert all(200 <= x['text_top'] < x['text_bottom'] <= 1300 for x in layouts), story_id
    # Decode the entire encoded stream to catch errors beyond metadata and sampled frames.
    result = subprocess.run([ffmpeg_path(), '-v', 'error', '-i', str(file), '-f', 'null', '-'], capture_output=True)
    assert result.returncode == 0 and not result.stderr.strip(), result.stderr.decode()
    results.append({'story_id': story_id, 'title': s['title'], 'path': str(file.resolve()),
                    'frames': count, 'fps': rate, 'seconds': count/rate, 'dimensions': [width, height],
                    'full_decode': 'passed', 'text_layout': 'passed', 'glow_words': s['glow_words'],
                    'boundary_frames': [119, 120], 'boundary_pixel_error': differences, 'clip_plan': p})
    previews.extend([(story_id + ' / 0–4s', samples[30]), (story_id + ' / 4–8s', samples[150])])
    review += [f"## {story_id} — {s['title']}", '', f"[Play video]({file.resolve()})", '',
               s['screen_1'].replace(s['glow_words'], '**' + s['glow_words'] + '**'), '',
               s['screen_2'], '', f"Footage: {p['opener']} → {p['closer']}", '']
    print(story_id + ' verified', flush=True)

for start in range(0, len(previews), 8):
    sheet = Image.new('RGB', (1440, 1352), '#18151b')
    d = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(previews[start:start+8]):
        x, y = (i % 4) * 360, (i // 4) * 676
        d.text((x+12, y+7), label, font=font, fill='white')
        sheet.paste(img.resize((360, 640)), (x, y+36))
    sheet.save(ROOT / f'contact-sheet-{start//8+1}.jpg')

(ROOT / 'render-review.md').write_text('\n'.join(review))
(ROOT / 'render-manifest.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
(ROOT / 'completion.json').write_text(json.dumps({'stories': 50, 'videos': len(results),
    'status': 'complete', 'format_checks': 'passed', 'full_video_decode': 'passed',
    'font': 'TikTok Sans', 'music_added': False, 'published': False}, indent=2))
print('All 20 outputs verified. Review index and contact sheets saved.')
