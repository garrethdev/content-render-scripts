# Cleora re-render + SuperWarm requeue (opener variety)

Context: see the Obsidian note `Operations/Cleora Opener Variety Governor.md` and `Operations/Handover - ...`.
The plan lives in the Supabase table `cleora_opener_plan` (`seq`, `action` keep/staged/rerender, `new_hook`).

## 1. Re-render (B6 episodes only; their voiceovers are the local `~/cleora-render/tts_epNNN.json`, ep060 = CLE-B6-0060)
```bash
export SUPABASE_KEY=<project anon key>            # read-only is enough
python3 rerender_b6.py                             # every B6 episode the plan marks 'rerender', in seq order
python3 rerender_b6.py CLE-B6-0003 CLE-B6-0056     # or specific ones
```
Output: `~/cleora-render/rerender_staging/CLE-B6-NNNN.mp4` (~65 s each). Nothing is uploaded or written to the database.

## 2. Queue on SuperWarm (newer renders only, in plan order)
```bash
export SW=<SuperWarm API key>  SUPABASE_KEY=<project anon key>
python3 superwarm_queue.py --dry                   # show what would be queued
python3 superwarm_queue.py                         # upload staged videos via SuperWarm and add them to the queue
```
Fills the queue up to its cap (36 pending), never touches posted items, uploads through SuperWarm's signed-URL flow
(the anon key cannot write to our storage bucket), and prints what it did. See the handover note for the DB bookkeeping.
