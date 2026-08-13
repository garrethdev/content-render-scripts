# Char3 ASMR "Weightlifting Question" lane

Recreation of IG reel `DbJi1GwJH2i`: a fast-ish montage of Char3 weightlifting-library
clips with a two-slide text overlay (question → payoff), for the Peptide Miracles
metabolic-health angle.

## Format / layout
- Vertical 1080×1920, **15–25s**, silent (music attached at post).
- **Montage** of `video_library` clips (`content_label=char3_weightlifting`, `phase=After`),
  **each clip used once** (no repeats), varied length + order, tightened to a mid-rep
  window, same-outfit clips grouped for continuity.
- **Two sequential text slides**, centered cream serif (Didot), upper third, soft top
  scrim + heavy drop shadow for legibility:
  1. **Hook** (question) — visible from t=0, **< ~2.5s**, then disappears.
  2. **Payoff** — appears when the hook clears, dwells ~4–7s (scaled to length), then
     disappears; the montage plays out with no text.
  - A trailing emoji on a payoff renders in colour (Apple Color Emoji).

## Pipeline
1. **Writing agent** (n8n `NOlaieLLePKs3HiN`) — generates question→payoff pairs into
   Supabase `char3_asmr_hooks`. See [WRITING_AGENT.md](WRITING_AGENT.md).
2. **Director-stitch** (n8n `HcMiA1ywOVhI20oh`) — writes a montage **blueprint** JSON onto
   each approved hook row. See [DIRECTOR_STITCH.md](DIRECTOR_STITCH.md).
3. **Render script** — [`render_char3_asmr_montage.py`](render_char3_asmr_montage.py)
   executes a blueprint (or self-blueprints) into the final mp4.

## Render usage
```bash
# self-blueprint from a hook number (no DB needed), clips in ./clips or $C3Q_CLIPS:
python3 render_char3_asmr_montage.py auto <hook_no> "<hook>" "<payoff>" out.mp4 [clipsdir]

# execute a blueprint JSON written by the n8n director:
python3 render_char3_asmr_montage.py blueprint blueprint.json out.mp4 [clipsdir]
```
`clips/` holds the local copies of the `char3_weightlifting` After-clips (not committed).

## Data
- `char3_asmr_hooks` (Supabase `qlcmgxgwpzmiebzxflai`): `hook_no, hook, payoff, batch,
  gate_status, used, blueprint jsonb, final_video`.
- Clip pool: `video_library` (`content_label=char3_weightlifting`, `phase=After`).

`render_char3_asmr_q.py` is the earlier single-clip proof renderer (superseded by the
montage renderer; kept for reference).
