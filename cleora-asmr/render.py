#!/usr/bin/env python3
"""Render explicitly selected stories over four local clips. No scoring or classification."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS = 1080, 1920, 30


def ffmpeg_path():
    found = shutil.which('ffmpeg')
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def words(text):
    return re.findall(r"\b\w+(?:[’'-]\w+)*\b", text)


def validate(stories):
    assert len({s['id'] for s in stories}) == len(stories), 'Duplicate story IDs'
    for s in stories:
        assert s['screen_1'].strip() and s['screen_2'].strip(), s['id']
        assert len(words(s['glow_words'])) == 2, s['id'] + ': choose two glow words'
        assert s['screen_1'].count(s['glow_words']) == 1, s['id'] + ': highlight must occur once'


def overlay(text, highlight, dest, regular, bold):
    """Keep the entire paragraph visible; only the selected phrase uses a bold face."""
    tokens = list(re.finditer(r'\S+', text))
    start = text.find(highlight) if highlight else -1
    end = start + len(highlight) if highlight else -1
    max_width = 790
    for size in range(58, 45, -2):
        fonts = [ImageFont.truetype(regular, size), ImageFont.truetype(bold, round(size * 1.10))]
        lines, line, length = [], [], 0
        for token in tokens:
            is_bold = start >= 0 and token.start() < end and token.end() > start
            font = fonts[int(is_bold)]
            width = font.getlength(token.group())
            gap = fonts[0].getlength(' ') if line else 0
            if line and length + gap + width > max_width:
                lines.append((line, length))
                line, length, gap = [], 0, 0
            if width > max_width:
                raise ValueError('A word is too wide to fit: ' + token.group())
            line.append((token.group(), is_bold, width, gap))
            length += width + gap
        if line:
            lines.append((line, length))
        line_height = int(size * 1.32)
        if len(lines) * line_height <= 790:
            break
    else:
        raise ValueError('Text exceeds the configured readable area; edit the paragraph.')

    height = len(lines) * line_height
    top = max(240, int(730 - height / 2))
    # Full-frame black scrim sits above footage and below the glow and text.
    # 51% opacity is 40% lighter than the previous 85% black scrim.
    base = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 130))

    ink = Image.new('RGBA', base.size)
    glow = Image.new('RGBA', base.size)
    d, gd = ImageDraw.Draw(ink), ImageDraw.Draw(glow)
    boxes = []
    for n, (line, length) in enumerate(lines):
        x, y = 465 - length / 2 + 65, top + n * line_height
        for token, strong, width, gap in line:
            x += gap
            font = fonts[int(strong)]
            if strong:
                gd.text((x, y), token, font=font, fill=(255, 255, 255, 255), stroke_width=6,
                        stroke_fill=(255, 255, 255, 230))
                boxes.append([round(x), y, round(x + width), y + line_height])
            d.text((x, y), token, font=font,
                   fill=(255, 255, 255, 255),
                   stroke_width=2 if strong else 3, stroke_fill=(12, 10, 14, 245))
            x += width
    # Reduce halo opacity by 20%; keep the white letterforms fully opaque.
    for radius in (18, 5):
        halo = glow.filter(ImageFilter.GaussianBlur(radius))
        halo.putalpha(halo.getchannel('A').point(lambda value: round(value * 0.8)))
        base = Image.alpha_composite(base, halo)
    base = Image.alpha_composite(base, ink)
    base.save(dest)
    return {'font_size': size, 'lines': len(lines), 'text_top': top,
            'text_bottom': top + height, 'highlight_boxes': boxes,
            'highlight_style': {'font_scale': 1.10, 'color': '#FFFFFF', 'glow_radii': [18, 5], 'glow_opacity_scale': 0.8},
            'backdrop_overlay': {'color': '#000000', 'alpha': 130, 'opacity': 130 / 255}}


def run(args, logfile):
    with open(logfile, 'w') as log:
        result = subprocess.run([ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y'] + args,
                                stdout=log, stderr=log)
    if result.returncode:
        raise RuntimeError(Path(logfile).read_text())


def prepare_segment(clip, offset, cache):
    import cv2
    source = Path(clip['path'])
    if not source.is_file():
        raise FileNotFoundError(source)
    cap = cv2.VideoCapture(str(source))
    rate, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if rate <= 0 or count / rate + 0.02 < offset + 4:
        raise ValueError('Clip is too short for the requested four-second segment: ' + str(source))
    key = hashlib.sha256(('exact-120-v2' + str(source.resolve()) + str(source.stat().st_mtime_ns) + str(offset)).encode()).hexdigest()[:16]
    target = cache / (key + '.mp4')
    if not target.exists():
        run(['-ss', str(offset), '-i', str(source), '-an',
             '-vf', f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1,fps={FPS},setpts=N/({FPS}*TB)',
             '-frames:v', '120', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
             '-pix_fmt', 'yuv420p', '-threads', '2', str(target)], cache / (key + '.log'))
    return target


def encode_exact_frames(first, second, folder, target):
    """Send exactly 120 composited frames per half; no independent overlay timestamps."""
    import cv2
    command = [ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', f'{WIDTH}x{HEIGHT}',
               '-framerate', str(FPS), '-i', 'pipe:0', '-an', '-frames:v', '240',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', '-threads', '2', str(target)]
    with open(folder / 'render.log', 'w') as log:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log)
        try:
            for half, source in enumerate([first, second], 1):
                text_layer = Image.open(folder / f'screen-{half}.png').convert('RGBA')
                capture = cv2.VideoCapture(str(source))
                try:
                    for frame_number in range(120):
                        ok, frame = capture.read()
                        if not ok:
                            raise ValueError(f'{source}: missing frame {frame_number}')
                        background = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA))
                        composited = Image.alpha_composite(background, text_layer).convert('RGB')
                        proc.stdin.write(composited.tobytes())
                finally:
                    capture.release()
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError((folder / 'render.log').read_text())
        except BaseException:
            proc.kill()
            proc.wait()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stories', type=Path, default=ROOT / 'stories-50.json')
    parser.add_argument('--plan', type=Path, default=ROOT / 'render-plan-20.json')
    parser.add_argument('--clips', type=Path, default=ROOT / 'footage/clips.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'renders')
    parser.add_argument('--ids', help='Comma-separated story IDs; default is the whole explicit plan')
    parser.add_argument('--overlays-only', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--regular-font', default=str(ROOT / 'fonts/TikTokSans-Semibold.ttf'))
    parser.add_argument('--bold-font', default=str(ROOT / 'fonts/TikTokSans-Extrabold.ttf'))
    args = parser.parse_args()
    stories = json.loads(args.stories.read_text())
    validate(stories)
    bank = {s['id']: s for s in stories}
    plan = json.loads(args.plan.read_text())
    if args.ids:
        selected = set(args.ids.split(','))
        plan = [p for p in plan if p['story_id'] in selected]
        if {p['story_id'] for p in plan} != selected:
            raise ValueError('Requested ID missing from the render plan')
    clips = {c['shot_key']: c for c in json.loads(args.clips.read_text())}
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / 'cache'
    cache.mkdir(exist_ok=True)
    results = []
    for index, p in enumerate(plan):
        s = bank[p['story_id']]
        folder = args.output / s['id']
        folder.mkdir(exist_ok=True)
        layouts = []
        for screen in [1, 2]:
            layouts.append(overlay(s[f'screen_{screen}'], s['glow_words'] if screen == 1 else '',
                                   folder / f'screen-{screen}.png', args.regular_font, args.bold_font))
        (folder / 'layout.json').write_text(json.dumps(layouts, indent=2))
        target = args.output / (s['id'] + '.mp4')
        fingerprint = hashlib.sha256(json.dumps({'story': s, 'plan': p,
            'script': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'fonts': [args.regular_font, args.bold_font],
            'clips': [(clips[p[k]]['path'], Path(clips[p[k]]['path']).stat().st_mtime_ns) for k in ['opener', 'closer']]}, sort_keys=True).encode()).hexdigest()
        receipt = folder / 'receipt.json'
        reusable = target.exists() and receipt.exists() and json.loads(receipt.read_text()).get('fingerprint') == fingerprint
        if not args.overlays_only and (args.force or not reusable):
            if not clips[p['opener']].get('can_open', True):
                raise ValueError('Plan uses a non-opening clip as the opener')
            first = prepare_segment(clips[p['opener']], p['opener_start'], cache)
            second = prepare_segment(clips[p['closer']], p['closer_start'], cache)
            temporary = args.output / (s['id'] + '.partial.mp4')
            encode_exact_frames(first, second, folder, temporary)
            temporary.replace(target)
            receipt.write_text(json.dumps({'fingerprint': fingerprint, 'story': s, 'plan': p}, indent=2))
        results.append({'story_id': s['id'], 'file': str(target.resolve()), 'layouts': layouts,
                        'status': 'overlays_ready' if args.overlays_only else 'rendered'})
        (args.output / 'latest-run.json').write_text(json.dumps(results, indent=2))
        print(f"{index + 1}/{len(plan)} {s['id']} " + results[-1]['status'], flush=True)


if __name__ == '__main__':
    main()
