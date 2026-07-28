# Diagnostic Hook — Pilot Spec (v1)

One video. Exact hook, kept verbatim. Testing the expert-diagnostic register for Peptide Miracles before scaling it into a lane.

## The hook (verbatim, do not rewrite)

> I can look at how you're trying to lose weight and within seconds spot why your metabolism isn't responding.

On-screen text overlay, centered upper-middle third. No VO on the hook. Let it sit 3 full seconds.

## Format

20-28 seconds. Text-over-b-roll. No talking character, no lip-sync.

| Beat | Time | On screen |
|---|---|---|
| Hook | 0-3s | Exact hook over continuous b-roll |
| Check 1 | 3-8s | "First thing I check: when you eat, not what." |
| Check 2 | 8-14s | "Second: protein at breakfast. Almost nobody passes this one." |
| Check 3 | 14-21s | "Third is the big one: whether food noise is running your day. That's the one nothing else fixes." |
| Close | 21-27s | "Yours is one of these three. The quiz finds which. Link in bio." |

Rules: one text card at a time. No lists on screen. Beat 3 is the peptide bridge — "food noise" only, never a compound name. The video never resolves which check is the viewer's — the quiz is the resolution.

## Visual

- ONE continuous candid clip, no cuts: woman mid-workout or mid-meal-prep, camera low or hip height, natural light, slightly imperfect framing. Subject is busy, not posing, not looking at camera.
- Reference: the Smith-machine screenshot (candid low-angle gym, subject working, golden light).
- Audience fit: cast/generate a Black woman 30-45 for our accounts.
- B-roll source options (pick one):
  1. Existing footage libraries (check filler_library and BA footage for a usable gym/kitchen clip)
  2. Generate via Seedance (BILLED — needs explicit approval with prompt + cost first)
  3. Shoot/source a real clip

## Text style

- Editorial serif, cream/off-white, subtle shadow, tight line height, centered. NOT the TikTokSans halo carousel style.
- Simplest native option: TikTok's built-in Serif text style.
- If rendering locally: Prata or Playfair Display (Google Fonts).

## Caption

"If your body stopped responding, one of these three is why. The quiz tells you which one. #weightlossjourney #foodnoise" (final hashtags per current account strategy)

## Compliance

- No drug or compound names anywhere. No "metabolism boost" claims from US. The hook's "metabolism isn't responding" is the viewer's own experience, stated back — keep it that way.
- No before/after bodies in this format. The authority is the calm, not the transformation.

## Before it posts (standing rules)

- Confirm batch id + notes, create content_batches row, tag the row (batch-tracking rule)
- Content rows go through n8n, not hand-written
- Any billed generation: prompt + payload + cost approved first

## What this pilot decides

If this single video holds watch-through and drives quiz clicks, the diagnostic register becomes the voice for all three formula test arms (YDIW / Reframe / Validation), same b-roll style, same serif, same quiz close.
