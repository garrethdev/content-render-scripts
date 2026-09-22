# The 40-episode slate — production run

The approved slate (48 written, 8 cut by the owner, 40 remain) driven from `cleora_content`
through voice to render. Episode numbers `ep501`-`ep540` map to content ids in `epmap.json`;
`ep501`/`ep502` keep the numbers they were first rendered under.

## Scripts

| file | what it does |
|---|---|
| `tts_prep.py` | `spoken()` — normalises a read for the voice clone (years, decimals, ranges, dates, acronym+digit, money, percent). The captions still show the raw script, so "1915" is on screen while she says "nineteen fifteen". |
| `b3_tts_prep.py` | Builds the four reads (hook / story / turn / closer) from a row's beats, picks `turn_at` at the burial beat, writes `<cid>.reads.json`. |
| `emit.py` / `rec.py` / `recurl.py` | Higgsfield TTS batching: emit a submit payload, record job ids, record result urls. Higgsfield caps 12 per submit and ~22 in flight, so the queue is worked in gated rounds. |
| `fetch.py` | Downloads finished reads into `audio/<ep>_<key>.wav`, the renderer's own cache slot. |
| `mktts.py` | Writes the per-episode `tts.json` the render wrapper takes, for every episode whose four reads have landed. |
| `drive.py` | Keeps N renders running, re-scanning as TTS lands, and deletes `assets/` + `renders/base.mp4` after each one (40 episodes at the full 356 MB each does not fit the disk). |
| `resplit.py` | Splits over-long body beats. See below. |

## Shot length: beat length IS shot length

The Director casts exactly one clip per beat and the renderer holds that clip for as long as its
beat is spoken. A beat written as one long evidence sentence therefore freezes the picture:

- 36 of 40 episodes had a shot over 6s
- 11 had a shot over 9s
- worst: ep512 (CLE-B4-0010) at **14.1s** on a single frame
- 110 body beats over 6s in total

Mostly the closing evidence beats ("In a 12-week trial of 50 women, the half treated with ...").

`resplit.py` splits a long beat at the sentence boundary nearest its middle, falling back to the
clause boundary (comma / semicolon / colon / dash) when the beat is one long sentence, recursively,
never leaving a side under 5 words. **Token order and count are preserved** — the concatenated body
text is byte-identical — so voice reads already generated from a script stay valid after a re-split;
only the beat boundaries move. Rows are reset to `written` so the Director re-casts one clip per beat.

A 14-word cap (~5.2s at her 2.7 words/sec) still leaves 8 episodes with a beat over 6.5s, because
those are single unbreakable sentences. A renderer-side hard cap is the missing backstop.

## Known state at the end of this run

- 39 of 40 episodes need the re-split; it has NOT been applied (dry run only).
- 22 of the 40 had no hook pair; the owner's seven built hooks were rotated across them, skipping any
  pair whose shots collide with that episode's first body clip (`../hooks/hook_pairs.json`).
- The Director had picked `hook03` for 15 episodes on its own — its "shocking historical discovery"
  tag matches nearly every story on this channel. Left as the Director cast it; needs an owner call.
- Four rows had failed at the *writer*, not the Director: two for the banned word "cure" in the TODAY
  beat, two for having no TODAY beat at all. The two "cure" beats were reworded; CLE-B5-0011 and
  CLE-B5-0017 still have no TODAY beat and so no "what you get" payoff.
- `female_scientist`, a shot the owner rejected, is still in ep502's EDL and about 21 others.
