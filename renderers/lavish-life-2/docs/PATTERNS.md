# PATTERNS — what separates picked from ignored (yara-dump)

Sets analyzed: 20 keepers vs 47 ignored (41 with the character + 6 character-less B-roll).
Every image in both sets was viewed at 560px, against the canonical face ref (char3/char3_car.png)
and sample real-creator frames (yara_gallery_src/thumbs). Key context: the dump is a
scene-by-scene recreation of the real creator's posts. The picks are the frames where the
recreation preserved the REAL photo's capture physics; the ignores are where it collapsed
into "AI model on a backdrop."

---

## Section 1 — The dividers, ranked

**1. Held pose vs candid beat — 36/41 ignored are held poses; 13/20 keepers have an active beat.**
The single strongest divider. Keepers are doing something: mid-laugh eyes closed (dump_04),
hand pushing through hair (dump_02), mid-stride with a water bottle (comp_24, dump_24),
interacting with a partner (comp_05/06/09/11), group energy (dump_33). Ignored images hold
a pose for the camera: symmetric stance arms down (dump_03), hand-on-hip catalog stance
(dump_01), touching the hat brim while gazing at lens (dump_05), over-shoulder butt pose
(dump_08), peace signs (dump_13, dump_52). The 7 static keepers all survive via divider #2.

**2. Light source declared and physically consequential — 20/20 keepers, ~18/41 ignored fail it.**
Every keeper's light has a visible cause AND visible consequences: hard sun -> specular sheen
on shoulders + hard cast shadow on the ground (dump_12, dump_04, comp_09, comp_24); on-camera
flash -> hard flash shadow thrown on the wall behind (comp_22); in-frame lamp/neon/LED
explaining the subject's color cast (dump_26, dump_32, comp_32). Ignored failures: face
evenly neutral-lit inside a warm candlelit room (dump_21, comp_31); frontally-lit subject
against a backlit sunset (dump_31); hand shielding the sun that casts no shadow on the face
(dump_10); flat inert light on a centered figure (dump_01, dump_03, dump_25, dump_27, dump_30).

**3. Background as PLACE vs background as BACKDROP — ~14/41 ignored are backdrop-flat; 18/20 keepers envelop.**
Keepers: geometry recedes PAST the subject (wine racks flanking both sides dump_29, hallway
floor lines comp_34, alcove + wall outlet + plant comp_32) or a foreground element clips the
frame (lounger corner dump_02, cabinet dump_04, umbrella rim comp_29/dump_19, lantern dump_32,
partner's shoulder comp_05-11). Ignored: subject parallel-parked in front of a flat plane —
hedge wall (dump_03, comp_25), wall niche (dump_27), wine-bottle wall (dump_30), plain hedge +
nothing in front (dump_06, dump_13).

**4. Best-of-set adjudication — at least 12 ignored are weaker near-dupes of a picked scene.**
The user was choosing within recreation sets, and the candid/light-correct variant won every
time: cowhide set -> dump_04 (laugh) picked over dump_05 + comp_25 (posed); wine cellar ->
dump_29 (receding racks, handbag) over dump_30 (flat bottle wall); neon entrance -> dump_32
over dump_44 (garbled "Gitano", cropped partner hand); street walk -> comp_24/dump_24 over
dump_48 (waxier skin, unnatural chest); golden-hour rail -> BOTH ignored (dump_14, dump_49:
editorial calm + face drift + sunglasses).

**5. Face on-model — ~9/41 ignored drift from canonical; keepers ~2/20 borderline.**
Clear ignored drift: comp_12 (younger, rounder, heavier makeup), comp_08 (face wider),
comp_10 (nose wider), comp_25 (chin smaller), comp_31 (face longer), dump_14 (narrower),
dump_34 (doll-smooth), dump_42 (squint-compressed), dump_11 (fuller). Face drift is heavily
concentrated in the couple selfies — the extra face seems to steal identity fidelity.

**6. Costume/merch matching sets — 5/41 ignored, 0/20 keepers.**
Every logo/monogram or his-and-hers coordinated look was rejected: LV denim suit + matching
bucket hat (dump_07, dump_52), denim-on-denim (dump_18), Fendi his-and-hers print
(comp_10), matching cream linen couple outfits (dump_45). Reads as costume/ad, not wardrobe.

**7. Sunglasses hiding the face — 6/41 ignored vs 2/20 keepers.**
Ignored: dump_13, dump_17, dump_23, dump_46, dump_47, dump_49. The 2 keeper exceptions
(comp_29, dump_19) are hat-styling selfies where the accessory IS the shot's subject.

**8. Cloned/repeating background modules — 4/41 ignored, 0/20 keepers.**
Identical backlit shelf niches (dump_28), umbrella/lounger rows (dump_17), blob topiary
(dump_41), kitsch heart-shaped topiary (dump_42).

**9. B-roll without the character — 6/6 ignored, 0 picked.**
dump_35-40 (sunset, pools, VS bag, Rolex wrist, dinner table) are actually the most
photoreal frames in the dump, but carry no character value. Note dump_39's long decorated
nails contradict the character's short nude nails everywhere else.

---

## Section 2 — The cutout anatomy

"Character cutout" = the simultaneous presence of most of these five ingredients:

1. **Unmotivated frontal light.** The subject is lit by an even, directionless beauty light
   while the scene has its own light story (sunset behind, candles, warm lamps). Subject and
   background were "rendered separately." This is the #1 ingredient — dump_31 and dump_21
   are pure cases.
2. **Catalog geometry.** Dead-center full body, squared shoulders facing lens, symmetric
   stance, feet together, camera at chest height with no tilt — the framing of a product
   photo, which nobody's friend actually shoots (dump_01, dump_03, dump_27).
3. **Backdrop parallelism.** The background is a flat plane behind the subject (hedge, wall,
   bottle wall) with nothing in front of her and no geometry receding past her — she sits ON
   the scene, not IN it (dump_30, dump_06).
4. **Missing contact evidence.** Weak or absent cast shadow, no floor interaction, a crisp
   uniform silhouette edge (sometimes with a faint halo), hem/feet mushing into the ground
   (dump_34).
5. **Zero time.** Nothing is mid-happening — no motion, wind, half-blink, mid-step, or
   object in use. A held expression at held-pose stillness reads as a render even when skin
   texture is good (dump_05 vs picked dump_04 is the cleanest A/B).

Any single ingredient is survivable; three or more = cutout.

## Section 3 — Why the free-standing keepers still pass

- **dump_12 (red one-piece, pool edge):** hard sun with a real cast shadow, specular sheen
  on skin, pool caustics interacting with light, feet with contact shadows, camera far +
  slightly low with true perspective. Static pose, but the LIGHT does all the anchoring.
- **dump_04 (cowhide + cowboy hat laugh):** mid-laugh eyes closed = time; hat casts real
  shade on the face; cabinet edge in foreground; sheen + hard shadows. Candid beat + light.
- **dump_02 (black one-piece, hand in hair):** motion beat + wind in hair; lounger corner
  clips the frame; soft overcast light correctly produces soft shadows.
- **comp_32 / comp_34 (marigold room):** the room WRAPS — alcove, receding hallway floor
  lines, wall outlet, plants, in-frame LED explaining the light. Mundane environmental
  detail = place, not backdrop.
- **comp_22 (flash in wine room):** the frontal light is EXPLAINED — on-camera flash fiction,
  and it throws a hard flash shadow on the wall behind her. Frontal light is fine when the
  image admits it's flash.

Rule extracted: a free-standing centered shot passes if it has (a) a declared light source
with visible consequences, AND (b) either a candid beat or an environment that recedes past
the subject. Anchoring alone was never the requirement — light honesty was.

## Section 4 — Per-ignored-image kill reason

**Catalog stance / flat inert light (the core cutouts)**
- dump_01: static hand-on-hip center-frame, flat frontal light, no beat
- dump_03: symmetric arms-down mannequin stance, waxy-smooth skin, hedge backdrop
- dump_27: centered against flat wall niche, stiff symmetric stance, poster composition
- dump_30: flat wine-bottle wall backdrop, even frontal light in a warm room, feet together
- dump_25: flat frontal light, awkward crop, weaker dupe of picked marigold-room set

**Subject-light vs scene-light mismatch**
- dump_21: face neutral-evenly lit inside warm candlelit restaurant
- dump_31: frontally-lit subject against backlit sunset on boat — pure paste
- comp_31: flat even face light in warm garden venue + face drift (longer)
- dump_10: hand shields the sun but casts no shadow on the face; overdone grin
- dump_34: doll-smooth face, saturated dress blob, hem/feet mush at ground

**Posed model-shoot energy**
- dump_05: posed hat-brim touch + direct gaze; lost to candid laugh dump_04
- dump_06: posed lean on stone table; athleisure + sun hat outfit mismatch
- dump_08: over-shoulder rear pose; staged IG-model shoot
- dump_13: peace sign + sunglasses; cliché and identity hidden
- dump_23: reclined editorial legs, sunglasses, face small
- dump_14: golden-hour rail lean, editorial calm, face drift (narrow), sarong pasted
- dump_49: dupe of 14 with sunglasses hiding face
- dump_45: matching linen couple, engagement-shoot posing, waxy abs on partner
- comp_03: reclined thirst pose, high-gloss thigh highlights; couple version picked instead

**Costume / merch sets**
- dump_07: LV monogram suit + matching hat; clone print costume
- dump_52: LV suit + peace sign; costume + cliché
- dump_18: denim-on-denim set; waxy white lip highlight
- comp_10: Fendi his-and-hers print; waxy hyper-defined abs; face drift

**Face drift (couple selfies concentrated)**
- comp_12: face clearly off-model — younger, rounder, heavier makeup
- comp_08: face wider; partner's skin uniformly oiled plastic
- comp_25: chin smaller; flat hedge; dupe of picked cowhide
- dump_42: face squint-compressed; kitsch heart topiary
- dump_11: face fuller; hazy blown background; waxy skin; thirst pose

**Cloned/AI background tells**
- dump_28: repeating identical backlit shelf niches
- dump_17: cloned umbrella/lounger rows + face hidden by hat+sunglasses
- dump_41: AI-blobby topiary hedge, flat light; weaker dupe of picked couple set
- dump_44: garbled "Gitano" neon, deep plunge, partner's hand awkwardly cropped

**Redundant with a picked variant (mild kills)**
- dump_15: seated yellow sundress; arm slightly elongated; flat hedge
- dump_16: yellow-suit lounger selfie; thirst pose; redundant with picked comp_11
- dump_46: red sports bra selfie; sunglasses; redundant pool selfie
- dump_47: brunch mimosa — actually strong; sunglasses + set redundancy
- dump_50: lounger selfie w/ hat; decent; redundant with yellow-dress set
- dump_20: bathroom arm-selfie without a mirror — odd camera fiction, sterile counter
- dump_09: both hands on hips at selfie distance — who is holding the phone?
- dump_43: over-shoulder date candid — strong; lost to venue set redundancy; doubled knives
- dump_48: walking candid; waxier skin, unnatural chest under tank; lost to dump_24/comp_24

**B-roll, no character (different class — skipped, not failed)**
- dump_35: boat sunset; dump_36: infinity pool dusk; dump_37: overcast pool; dump_38: VS bag
- dump_39: Rolex wrist — NOTE long decorated nails contradict character's short nude nails
- dump_40: dinner table

## Section 5 — PROMPT RULES v2

**ADD to every generation prompt:**
1. Name the photographer fiction explicitly: "phone selfie taken by her partner, his
   shoulder and arm edge in frame" / "friend photographing her from ~3m with an iPhone,
   chest height, slightly tilted, casual framing."
2. Declare the light source AND its consequences in the same sentence: "hard midday sun
   from upper left — glossy sheen on her shoulders and collarbone, hard cast shadow on the
   pavement behind her" / "direct on-camera flash at night — hard flash shadow thrown on
   the wall behind her" / "lit by the warm lamp visible in frame, warm cast on the near
   side of her face."
3. Give her a candid beat, one per image: mid-laugh eyes closed, tucking hair behind ear,
   mid-stride, adjusting her hat, raising a mimosa, hand mid-motion through hair.
4. Put one thing in FRONT of her: lounger corner, table edge, lantern, umbrella rim,
   partner's shoulder, doorframe — clipping a frame edge.
5. Make the environment recede PAST her on at least one side (path, racks, hallway,
   pool edge running into depth), never a flat plane directly behind her.
6. Contact evidence: feet/body with visible contact shadows; hem and shoes fully resolved.
7. Imperfection budget (pick 2): construction cranes, background bystanders, wall outlet,
   scuffed tile, off-center framing, cropped limb, water bottle or handbag in hand.
8. Face: match reference exactly, no beautification, minimal makeup, short nude nails.

**BAN:**
- Centered full-body, squared to camera, symmetric stance, hands at sides or on hips,
  against a flat hedge/wall/backdrop ("catalog stance").
- Even frontal beauty light inside any scene with its own light story (sunset, candles,
  warm interior). If the light must be frontal, make it an admitted flash with a wall shadow.
- Matching logo/monogram outfit + hat sets; his-and-hers coordinated outfits.
- Peace signs, over-shoulder rear poses, hat-brim-touch gaze, brow-shield without shadow.
- Sunglasses covering the eyes, except in a hat-styling selfie where the accessory is the point.
- Repeating background modules: umbrella rows, shelf niches, cloned loungers, topiary shapes.
- Legible signage longer than ~7 characters (garbles); heart/novelty topiary.
- Rendering the partner with uniform oiled sheen or hyper-defined abs (waxy tell).

## Section 6 — Keeper watch-list

- **dump_33 (group shot):** the three other women's faces are small and slightly generic;
  fine at feed size, avoid cropping in.
- **comp_29 / dump_19 (hat selfies):** sunglasses hide the eyes — face consistency
  unverifiable; acceptable as styling shots, don't let this become the norm.
- **dump_24 (statue walk):** face reads slightly rounder/younger than canonical — borderline;
  the closest a keeper comes to drift.
- **comp_34 (marigold room wide):** the buddha wall painting is slightly melty on close look.
- **dump_32 (neon entrance):** "Gaetano" letterforms mildly wobbly — passes, but signage is
  a standing risk.
- **comp_09 / comp_11 (couple selfies):** partner's skin runs glossier than hers; watch that
  the partner doesn't go waxy in future gens (that's what killed comp_08/comp_10).
- **comp_22 (flash wine room):** left-hand fingers slightly soft at full resolution; flash
  look otherwise carries it.
