"""pictures.py: the picture plan for the Camera Roll Story lane (Character 6, eight slides). Version 2.

Garreth, 2026-11-18, on version 1: "relies on too much literal imagery", "images of her only its
boring", "we need to use other images in the library". Version 1 matched each picture to its line
and showed her on nearly every slide.

THE PLAN NOW. A picture carries the mood of its beat, and most of the middle is her world, not her:
  1  hook           her before, a face that stops the scroll
  2  the scene      \
  3  turning inward  |  five slides: three or four pictures with no person (her kitchen, her food, a mug
  4  what she tried  |  in two hands, the takeout on the coffee table, a field, the evening sky, the
  5  a kind person   |  pharmacy bag by the peonies) and one or two of her before. The arrangement
  6  she starts     /   changes from deck to deck so a batch does not look stamped out.
  7  first reveal   her now, close or waist up
  8  full reveal    her now, at full length

Her slimmer body is held for slides 7 and 8 (slide 8 alone when a story sets reveal_from = 8).
Every picture comes from the Character 6 library, the files under rich-life-images/character-6/.
The renderer refuses any picture stored anywhere else. (A first try on 2026-11-18 also used
universal-images and the IMG set; Garreth said those are outside the library.) Pictures that show another woman's body, luxury
brands or an injection pen are left out, and so are the shared pictures that show someone
else's hands or legs (the mug in two hands, the slippers, the journal, the hotel bed).
"""

BEFORE, AFTER, OBJECT = "before", "after", "object"

# arrangements of slides 2..6: O = a picture with no person, H = her before
LAYOUTS = ["OHOOO", "OOHOO", "HOOOH", "OOOHO", "OHOHO", "HOOOO", "OOHOH", "OOOOH"]

# ---- pictures with no person, by the mood of the beat (slide number -> photo ids, best first)
OBJ = {
    2: [194, 167, 213, 212, 166, 195, 181, 164, 163, 169],                  # the scene: her world, a place
    3: [327, 211, 195, 181, 190, 182, 213, 196],                            # inward: low, quiet, alone
    4: [165, 161, 204, 216, 219, 196, 200, 201, 207, 189, 215, 185, 217],   # what she tried: plates
    5: [167, 194, 166, 205, 197, 198, 212, 213, 202, 168],                  # a kind person: a table, cake, a cafe
    6: [198, 190, 182, 211, 195, 194, 160, 162, 203, 218, 220, 164],        # she starts: small quiet things at home
}

# ---- her before, by beat. Garreth, 2026-11-18: "images of her before the reveal should be of her larger".
# So every photo here shows her body (full length, seated or waist up and wide). Close face selfies,
# where her size cannot be seen, are not used before the reveal.
HER = {
    1: [300, 405, 415, 413, 312, 313, 404, 417, 402, 412, 416, 341, 311, 309, 310, 419, 403, 316],
    2: [312, 313, 404, 417, 402, 416, 405, 415, 309, 310, 314, 318, 324, 403],
    3: [341, 306, 300, 317, 413, 412, 311],
    4: [305, 322, 321, 302, 420, 310, 309],
    5: [304, 333, 318, 324, 314, 311],
    6: [306, 341, 317, 311, 322, 300],
}

# ---- her now. Stories name these two (stories.json "shots", last two entries).
NOW = {
    "now_close":  [134, 135, 139, 278, 238, 144, 143, 132, 297, 136, 153, 186],
    "now_home":   [135, 139, 238, 278, 134, 262],
    "now_out":    [292, 151, 144, 143, 132, 145, 133, 138],
    "now_active": [284, 295, 170, 271, 297, 252],
    "now_mirror": [121, 224, 122, 127],
    "now_full":   [148, 150, 147, 159, 210, 274, 146, 152, 224, 127, 128, 121],
    "now_dress":  [148, 274, 150, 224, 144],
    "now_swim":   [208, 209, 239],
    # a story that holds the reveal to slide 8 shows her before on slide 7
    "mirror_before": [300, 305, 341],
}
FALLBACK_NOW = {7: "now_close", 8: "now_full"}
MAX_USES = 3
DEFAULT_REVEAL_FROM = 7

# pictures worth having made (code, what it shows, why)
WANTED = [
    ("W01", "A child's birthday cake with candles lit, small hands at the edge of frame", "scene slides about family days"),
    ("W02", "A printed photo held to a fridge door by a magnet", "closing slides"),
    ("W03", "A bicycle leaning on a garage wall in morning light", "the slow change"),
    ("W04", "A phone face down on a kitchen counter beside a mug", "inward slides"),
    ("W05", "Clothes heaped on a bed, a mirror edge in frame", "inward slides about getting dressed"),
    ("W06", "A dressing room curtain with clothes over the rail", "scene slides"),
    ("W07", "A pool deck with towels and a child's float, nobody in frame", "scene slides"),
    ("W08", "Two coffee cups on a cafe table, one chair pushed back", "a kind person"),
    ("W09", "A small dish by a kitchen sink with a ring in it", "inward slides"),
    ("W10", "A winter coat on a hook by a front door", "closing slides"),
    ("W11", "Her before with one friend, talking, both in frame (we have two)", "a kind person"),
    ("W12", "A plain pharmacy bag on a kitchen table, no flowers or jewellery", "she starts"),
]
