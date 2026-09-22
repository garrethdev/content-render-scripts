# Cleora music beds

Canonical home of the episode music. The Director picks one bed per episode
(stored in `cleora_content.edl.music`); the render wrappers read them from
`{BATCH}/assets_music/` — symlink or copy this folder there.

Expected files (source of truth was `~/cleora-render/cleora-batch/assets_music/`
on the render machine):
- `owner_song_01.mp3` — short, sparse, brighter/lighter (never yet picked)
- `owner_song_02.mp3` — long, slow, dark and low (betrayal/money stories)
- `owner_song_03.mp3` — long, slow, fuller and warmer (the workhorse, ~75% of episodes)
- `music_bed.wav`     — composed Golden-Brown-esque default/fallback bed

To backfill from the render machine:

    cp ~/cleora-render/cleora-batch/assets_music/*.mp3 ~/cleora-render/cleora-batch/assets_music/music_bed.wav cleora/assets_music/ 2>/dev/null
    git add cleora/assets_music && git commit -m "Add Cleora music beds" && git push
