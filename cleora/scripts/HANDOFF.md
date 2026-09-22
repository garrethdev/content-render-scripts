# Where the on-screen text actually comes from

## The correction

`cleora_content.hook_text` is **not** a defect. It is meant to hold the
spoken hook — the Writing Agent sets `hook_text = beats[0].vo` by design.

The on-screen text is a different field: `script.on_screen_hook`. The
Writing Agent's own prompt is explicit that it "must NEVER just repeat or
paraphrase" the spoken hook, and gives worked pairs:

> spoken: "Some of your skin cells stopped working years ago and will not die, darling."
> on screen: THE SKIN CELLS THAT WON'T DIE

So the earlier reading — "101 stories have a card that copies the voice" —
was measuring the wrong field. Those rows have no on-screen text at all,
because the field was never populated.

## Why it was never populated

`[Cleora] Writing Agent` (XExs9ffnqdh0Un4i) had a **v5 draft** carrying
`on_screen_hook`, the `cta` field, the dejargon rule and hook-device
rotation. It was never published. The **active version was still v3**,
which has none of them.

Published v5 on 2026-09-07. Nothing else needed writing.

## The blocker

The agent cannot run. Its Anthropic credential — **"Anthropic account"**
(`2h6vZlL0eISF1EsT`) — returns:

> Your credit balance is too low to access the Anthropic API.

`[Cleora] Story Research` uses a different credential, **"Anthropic
account 2"** (`PB0eoyieziAMdZWf`), which still has credit and ran fine the
same day. So either top up the first account, or point the Writing Agent
at the second.

Until then the agent errors every five minutes and writes nothing.

## Batch 5 is staged for the agent, not finished

The 18 rows sit at `script_status = 'pending'`, which is exactly what the
Writing Agent consumes. Their `notes` now carry the full scout research
(anchor, mechanism, felt symptom, action), so the agent has real facts to
write from rather than a one-line brief.

When credit returns it will rewrite all 18 in the v5 shape, with the
on-screen hook and CTA the hand-written versions do not have. That is the
intended outcome — the hand-written scripts in `BATCH5.md` and
`batch5_rows.json` are kept only as a fallback.

## Still open: the 30 approved stories

They have finished, approved scripts and no `on_screen_hook`. The Writing
Agent regenerates a whole script from a brief, so running it over them
would discard work the owner already approved. Adding just the on-screen
hook to an existing script is a different job and does not exist yet.
