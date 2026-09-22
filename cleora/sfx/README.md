# Sound effects on the episode timeline

`sfx.py` lays an effect onto a **fully rendered** episode and records the placement as a track in that
episode's `artifacts/edit_decisions.json` — OpenMontage's timeline document, the same file that already
carries the picture cuts and the hook-card overlay. The placement is data, not a shell command that
vanishes, so it can be reviewed, diffed and re-run.

```
python3 sfx.py --ep ep503 --source Ringtone.mp4 --seconds 4 --fade 1.5 --gain -12.4 --at 0.0
```

| flag | meaning |
|------|---------|
| `--ep` | rendered episode to lay the effect onto |
| `--source` | the effect file; video or audio, only the audio stream is used |
| `--seconds` | absolute clip length kept **from the start** |
| `--keep` | same thing as a fraction — `0.2` chops off the last 80%. `--seconds` wins if both are given |
| `--fade` | fade-out length ending at the out-point, so the effect *leaves* instead of stopping dead |
| `--at` | timeline second to fire it, repeatable for multiple hits |
| `--gain` | dB relative to the episode mix; negative sits it under her voice |

Volume in dB, since owners think in percentages: **−6 dB is half**, **−4.4 dB is down 40%**,
**−8 dB is down 60%**. To take an existing placement down 40%, add −4.4 to its current `--gain`.

## What it does

1. **Trim** — keeps the head of the source and fades out into the cut, so the effect leaves rather than
   stopping dead. A `--fade` longer than the clip is clamped to the clip.
2. **Timeline** — the effect becomes a **full-length SFX bed**: silence everywhere except the hits.
   OpenMontage's `AudioMixer` (`operation: extract`) pulls the episode's audio, and `operation: mix`
   layers the bed under it, then re-normalises to −14 LUFS for TikTok.
3. **Lay it back on the picture** — OpenMontage's `VideoCompose` (`operation: compose`), the same tool
   that assembled the episode, takes the finished render as a single cut and the new mix as its audio.
   Written as `<ep>_sfx.mp4`; the original render is never overwritten.
4. **Record** — an `audio_tracks` entry naming the original source, the fraction kept, the clip length,
   the gain, and every hit's start/end second.

## Why the bed has to be full length

`amix` divides every input by the input count and uses `dropout_transition` to ramp the survivors back
up when a short input ends. A 6 s effect over a 56 s episode therefore ducks her voice by 6 dB for
**exactly as long as the effect plays** — the duck cancels the effect out, and the finished file measures
the same at the hit as it does anywhere else. Padding the bed to the episode's length makes the halving
uniform, which the `loudnorm` stage then undoes.

The same trap is already documented in `AudioMixer._segmented_music`, which passes `normalize=0` for this
reason. `_mix` and `_full_mix` do not. `_full_mix` gets away with it because its two tracks run the same
length; `_mix` does not, so callers layering a short effect must pad it themselves.

## Verified on ep503

Owner's settings: 4.0 s, 1.5 s fade, −12.4 dB.

| bed window | level |
|---|---|
| 0–1 s | −29.0 dB |
| 2–3 s | −29.3 dB |
| 3–4 s | −39.5 dB (fading) |
| after 4 s | −91 dB (silence) |

So the effect holds, ramps down across the last 1.5 s and is gone at 4 s. In the finished file the head
window gains **+0.8 dB** against control windows at +0.5 and +0.6 dB, and her voice does not duck.
