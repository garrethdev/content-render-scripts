# Batch 5 scripts

Eighteen scripts written from the candidates the owner kept on the long
list board. One file per six scripts, plus `assemble.py` to turn them
into `cleora_content` rows.

```bash
python3 assemble.py          # -> batch5_rows.json
```

## Shape

Matches the owner-approved CLE-B4 rows: 13 beats, 150-195 words, beat
kinds running `pain -> flip -> story -> burial -> today -> identity`
across slots `hook / body / closer`, every beat carrying its own
uppercase `caption`.

## The opening card is not the opening line

On the existing approved rows, `hook_text` is a byte-for-byte copy of
`beats[0].vo`. That gives the viewer a subtitle of what they are already
hearing and wastes the most valuable strip of screen in the video.

Every row here carries a card written separately from the voiceover —
usually the place and the year (`OITA, 1978. MINUS 166 DEGREES.`) while
the voice opens on the viewer's own body. `assemble.py` asserts the two
are different and prints the check.

## Status

Inserted as `script_status = 'pending'`, deliberately. The Director polls
every five minutes for `written` and would otherwise start assigning
clips before the owner has read a word. Flipping the batch to `written`
is what releases it:

```sql
update public.cleora_content set script_status='written'
where batch_id='cleora-b5';
```

Allowed values are `pending`, `written`, `scripted`, `failed` — a check
constraint rejects anything else, `draft` included.

## Care taken on three of them

- **The Pill That Burned Too Hot** (DNP) — still sold online, still kills
  people every year. The script says so twice and tells the viewer not to
  go looking. It is a history, not a suggestion.
- **The Old Man And The Syringe** — Brown-Sequard's extract had almost no
  active hormone; the script says plainly that he talked himself young,
  then makes the real point about hormones falling with age.
- **Ten Days To A New Coat** (FOXO4-DRI) — a 2017 mouse study. The script
  names it as a mouse study and warns that anyone selling it is selling a
  mouse study.
