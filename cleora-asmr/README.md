# Madame Cleora production batch

This folder contains 50 story drafts, an explicit selection of 20, the four supplied ASMR clips, and a local renderer. Nothing is uploaded or published by the renderer. There is no scoring model, content classifier, approval gate, or hidden story selection.

## Read and review

- `stories-50.md`: all 50 stories, with the two highlighted words in bold.
- `stories-50.json`: the same text for agent handoff or editing.
- `best-five-worst-five.md`: the ten complete stories requested for editorial comparison, with reasons.
- `render-plan-20.json`: the exact story IDs, opening/closing clips and source offsets selected for rendering.
- `render-plan-50.json`: an explicit plan for every story, if you later choose to render the rest.
- `text-previews/`: both ready-to-use text overlays for all 50 stories.
- `renders/MC-###.mp4`: finished eight-second videos.
- `renders/MC-###/`: transparent text overlays, layout measurements and render receipt.
- `render-review.md`: links to the 20 outputs, generated after rendering.

The bank retains the previous 20 drafts and adds 30, including the Finsen direction. The older first-five batch is not added separately. Source carousel IDs are recorded per story; the original synced sources are unchanged. The new extraction contains 346 slides from 29 further carousels. The broccoli-sprout story uses previously extracted p148.

## Visual treatment

1080 × 1920 portrait, 30 frames per second, exactly 240 frames. Each full paragraph appears immediately and stays on screen for four seconds. The footage and paragraph cut together at four seconds. No typing animation, captions appearing one word at a time, fades between paragraphs, narration, music or sound effects are added.

The font is the official open-source TikTok Sans, with white letters and a dark outline to follow the supplied reference. Body text uses weight 600; exactly two words on screen one use weight 800 and a soft warm glow. Text wraps and sizes to fit the readable area. A full-frame black overlay at 51% opacity sits between the footage and text, making the backdrop 40% lighter than the previous overlay. The source clips are 480p/720p portrait; exporting at 1080p does not create additional source detail.

The two opening shots are cauldron-stir and walk-to-cauldron. The two closing shots are flask-mixing and ladle-tasting. The plan rotates all four pairings and varies source offsets. These are 20 stories made from four recurring shots, not 20 new animations. Outputs are silent, as requested for music to be added later.

## Run locally

From this folder:

```sh
python3 render.py
```

Render a particular selected story:

```sh
python3 render.py --ids MC-026
```

Create text overlays without encoding videos:

```sh
python3 render.py --overlays-only
```

All 50 stories have already been laid out successfully. To render one of the other 30, use the full-bank plan, for example:

```sh
python3 render.py --plan render-plan-50.json --ids MC-028
```

Existing matching outputs are reused. Changes to the story, plan, script or footage invalidate the corresponding receipt. `--force` rerenders selected outputs. Other arguments: `--stories`, `--plan`, `--clips`, `--output`, `--regular-font`, `--bold-font`.

Dependencies already used in this workspace: Python 3, Pillow, OpenCV, and imageio-ffmpeg (or an installed FFmpeg). No service keys or paid models are needed. The bundled static TikTok Sans instances were generated from the official variable font at weights 600 and 800; the license is retained in `fonts/OFL.txt`.

To render another story, explicitly add its ID and a valid four-second pair of source segments to the plan. The renderer validates text layout and input lengths; it does not judge content. `expand_stories.py` is the initial bank-building source: edit `stories-50.json` directly for production revisions, and do not rerun the builder unless you intend to restore that initial bank.

## Prompt for another local agent

> Open the Madame Cleora production folder. Read stories-50.json and render-plan-20.json. Use the existing render.py to render the selected stories with the four clips listed in footage/clips.json. Keep every story as two full four-second text blocks and highlight exactly its two glow_words on screen one. Use the bundled TikTok Sans fonts and preserve the eight-second format. Make only the text or plan changes I explicitly request. Save outputs locally and return links to the finished MP4 files. Do not add classifiers, grading, music, narration or publishing steps.

Local folder: `/Users/garreth/.codex/.chatgpt-projects/g-p-6aa04c3f9b8081919a18f7f1dc51a98c/outputs/miss-cleo-production`.

## Provenance

Footage URLs and local paths are in `footage/clips.json`. User supplied: Supabase story-finder, public cleora-clips/asmr, records 140–143. No database credentials were needed or accessed.

Font: https://github.com/tiktok/TikTokSans and https://github.com/google/fonts/tree/main/ofl/tiktoksans. TikTok's description: https://developers.tiktok.com/blog/tiktok-sans-open-source.

Stories are creative source adaptations for review. No independent claim-check pass or automated grading was performed in this batch. The best/worst comparison is the requested editorial assessment, not a performance measurement.
