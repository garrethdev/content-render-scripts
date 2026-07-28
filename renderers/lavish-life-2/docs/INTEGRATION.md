# Diagnostic Lane — Pipeline Integration Plan (SHELVED 7/25 — user called it: no new footage, no new end-to-end lanes. The angles run as covered-eye pillars instead; see chat. This doc kept for reference only.)

Format recap: 20-28s text-over-b-roll video. Serif hook card + 3 check cards + quiz close over ONE continuous candid clip. No character, no VO, no lip-sync. Hook bank: HOOK_BANK.md (24 approved hooks, 6 angles).

## Answers to the three questions

**New n8n?** Yes, but only ONE new workflow to start:
- "[Diagnostic] Body Writer" — clone of the covered-eye scriptwriter pattern (webhook + manual trigger, Sonnet 5, reads rows where beats are NULL, writes beat_2..4 + close + caption, sets gatekeep pending). Prompt = PILOT_SPEC structure + the graded taste rules (small observable moment, keep mystery, no villains, no failure predictions).
- NO hookmaker yet. The bank covers ~24 posts. Build "[Diagnostic] Hookmaker" (clone of covered-eye hookmaker, taste rules as system prompt) only when unused hooks < 10.
- NO new posting infra. Registers as a video type like the other lanes.

**More images?** No. A tiny VIDEO b-roll pool, not images — and tiny means TINY:
- **Pilot: 1 clip. Launch: 3-5 clips total.** The text carries the format; the same clip reruns with different hooks. At 2-3 posts/week, 5 clips = a month of posts before any repeat, and repeats don't matter because the hook is the content.
- Variety later is earned, not upfront: add 1-2 clips per week ONLY if the lane performs.
- Source order: (1) mine existing libraries first (filler_library, unused BA/source footage); (2) one yt-dlp session grabs 5 candidates in an hour; (3) Seedance last (billed, per-submit approval).

**New text hook writers?** Not yet (bank is stocked). When needed, the hookmaker is a small clone with the taste rules baked in. Hooks NEVER regenerate without user approval (standing dating-lane rule applies here too).

## What gets reused (the whole point)

| Piece | Reuse from |
|---|---|
| Renderer base | viral-filler-render-test/render_one.py (text over library clip) + dating-reaction/batch_render.py patterns |
| Clip pooling | video-tagger skill + filler analyze-once cache pattern |
| Writer workflow shape | covered-eye scriptwriter (MZya2jqP4MsERTMb) as template |
| Table shape | covered_eye_carousel / embarrassed_angle_content pattern: DG-### ids, hook_text, beat_2..4, broll_ref, caption, approved/gatekeep/batch/posting fields |
| Registry | content_type_registry row `diagnostic_video`, active=false until proven |
| Gate | Manual approval (user) initially — universal gate only scores carousel_copy |
| Batch rule | DG- prefix batches in content_batches |

## New build (small)
1. Renderer extension: sequential timed serif text cards on video (render_one.py overlays one hook; this needs 5 cards with timing). Download Prata + Playfair Display to ~/Library/Fonts (not installed — checked 7/25). ffguard-wrapped.
2. Supabase table `diagnostic_content` + seed the 24 bank hooks via an n8n load (not hand-inserted — pipeline rule).
3. The Body Writer workflow (above).

## Build order (gated on pilot)
1. **PILOT FIRST, zero infra:** 1 clip + one-off render of PILOT_SPEC.md + post on a test account with a batch id. If it doesn't hold attention, we spent nothing.
2. If pilot hits: table + seed bank + Body Writer + tag the b-roll pool + productionize renderer + registry row (inactive), first real batch DG-B1.
3. Hookmaker only when the bank runs dry.

## Approval gates (standing rules)
- n8n workflow creation/edits: proposed here, built only on explicit go
- Any Seedance/billed b-roll: prompt + payload + cost approved per submit
- Batch id confirmed before any content run
