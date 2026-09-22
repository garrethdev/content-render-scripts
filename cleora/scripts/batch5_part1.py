# -*- coding: utf-8 -*-
"""Scripts 1-6 of batch 5. Shape matches the owner-approved CLE-B4 rows:
12-13 beats, ~190 words, pain -> flip -> story -> burial -> today -> identity."""

S = {}

S["eight-people-locked-in-a-glass-dome"] = dict(
title="The Eight Sealed In Glass",
card="TWO YEARS. ONE DOME. NOT ENOUGH FOOD.",
beats=[
 ("You are eating less than you did at thirty and the weight will not move, darling.", "pain", "hook", "EATING LESS. STILL STUCK."),
 ("Eight people were sealed in a glass dome and accidentally proved something about that.", "flip", "body", "SEALED IN FOR TWO YEARS"),
 ("Arizona desert, 1991. Biosphere 2, a giant greenhouse locked from the inside.", "story", "body", "ARIZONA, 1991"),
 ("One of the eight was Roy Walford, a gerontologist who studied why bodies age.", "story", "body", "A DOCTOR OF OLD AGE"),
 ("Then the crops failed. The crew dropped to under two thousand calories a day.", "story", "body", "THE CROPS FAILED"),
 ("Walford did not call for help. He started taking blood.", "story", "body", "HE TOOK BLOOD INSTEAD"),
 ("Over two years they lost a tenth to a fifth of their body weight.", "story", "body", "A FIFTH OF THEMSELVES"),
 ("Blood pressure, cholesterol, blood sugar and inflammation all fell to numbers seen in lab animals bred to live long.", "story", "body", "NUMBERS FROM LONG-LIVED ANIMALS"),
 ("It was an accident inside a sealed building, so it was never a proper trial.", "burial", "body", "AN ACCIDENT, NOT A TRIAL"),
 ("Eight people is eight people. And they came out thin, tired and arguing.", "burial", "body", "THEY CAME OUT ARGUING"),
 ("Eating less without going short on nutrients is still the most repeated life-extension finding in animals.", "today", "body", "STILL THE MOST REPEATED FINDING"),
 ("In humans it has never been proven to extend life, and starving yourself is not the lesson, darling.", "today", "body", "NOT PROVEN IN PEOPLE"),
 ("Your body was not failing you. It was doing exactly what it does when the food runs out.", "identity", "closer", "IT WAS DOING ITS JOB"),
])

S["the-2-168-year-old-diet-found-in-a-tomb"] = dict(
title="The Diet Sealed In A Tomb",
card="SEALED 168 BCE. A DIET MANUAL.",
beats=[
 ("Your hunger does not switch off any more, no matter what you take away, darling.", "pain", "hook", "HUNGER THAT NEVER STOPS"),
 ("Someone wrote a manual about that and had it buried with her.", "flip", "body", "BURIED WITH HER"),
 ("Hunan, China, 1973. Archaeologists open Tomb 3 at Mawangdui.", "story", "body", "MAWANGDUI, TOMB 3"),
 ("It had been sealed since 168 BCE for the family of the Marquise of Dai.", "story", "body", "SHUT FOR 2,168 YEARS"),
 ("Inside, on silk, a text called Quegu Shiqi. Eliminating Grain and Eating Qi.", "story", "body", "ELIMINATING GRAIN"),
 ("It is the oldest known diet manual on earth.", "story", "body", "THE OLDEST DIET MANUAL"),
 ("Drop the five grains completely. Live on breath and one specific fern root.", "story", "body", "BREATH AND ONE ROOT"),
 ("The Taoists believed grain fed three worms in the gut that caused hunger, decay and age.", "story", "body", "THREE WORMS IN THE GUT"),
 ("Starve the worms, they wrote, and the body grows light again.", "burial", "body", "STARVE THEM. GROW LIGHT."),
 ("There are no worms. That part is simply wrong.", "burial", "body", "THERE ARE NO WORMS"),
 ("But cutting grain and eating in a narrow window is the shape of every modern fasting protocol.", "today", "body", "THE SHAPE OF MODERN FASTING"),
 ("They had the practice twenty-one centuries before anyone had the reason, darling.", "today", "body", "PRACTICE BEFORE REASON"),
 ("Your hunger is not weakness. It is older than the writing that tried to tame it.", "identity", "closer", "OLDER THAN THE WRITING"),
])

S["the-72-year-old-who-injected-himself-with-gland-extract"] = dict(
title="The Old Man And The Syringe",
card="PARIS, 1889. HE INJECTED HIMSELF.",
beats=[
 ("Your strength is leaving quietly and nobody has offered you anything for it, darling.", "pain", "hook", "STRENGTH LEAVING QUIETLY"),
 ("In 1889 one of Europe's great scientists stood up and said he had fixed that in himself.", "flip", "body", "HE SAID HE HAD FIXED IT"),
 ("The first of June, 1889. The Society of Biology in Paris.", "story", "body", "PARIS, 1 JUNE 1889"),
 ("Charles-Edouard Brown-Sequard, seventy-two years old, respected across the continent.", "story", "body", "SEVENTY-TWO YEARS OLD"),
 ("He told the room he had been injecting himself with crushed extract of dog and guinea pig testicles.", "story", "body", "HE TOLD THEM WHAT WAS IN IT"),
 ("His strength was back. His mind was sharp. He felt thirty years younger.", "story", "body", "THIRTY YEARS YOUNGER"),
 ("Europe laughed at him. They laughed for the rest of his life.", "story", "body", "EUROPE LAUGHED"),
 ("They were right to. Modern testing found almost no active hormone in his mixture at all.", "burial", "body", "ALMOST NO HORMONE IN IT"),
 ("A seventy-two-year-old man had talked himself young. That is all it was.", "burial", "body", "HE TALKED HIMSELF YOUNG"),
 ("But the idea underneath was correct. Hormones fall with age, and restoring them changes how old a body feels.", "today", "body", "THE IDEA WAS CORRECT"),
 ("Medicine needed decades to come back round to what the laughing-stock had said.", "today", "body", "DECADES TO COME BACK"),
 ("He was wrong about his syringe and right about his body, darling.", "today", "body", "WRONG SYRINGE. RIGHT BODY."),
 ("Being early and being ridiculous have always looked the same from the outside.", "identity", "closer", "EARLY LOOKS LIKE RIDICULOUS"),
])

S["the-chamber-that-lengthened-telomeres-in-ninety-days"] = dict(
title="The Chamber Built For Divers",
card="TEL AVIV, 2020. NINETY DAYS.",
beats=[
 ("You suspect you are older on the inside than you look on the outside, darling.", "pain", "hook", "OLDER INSIDE THAN OUT"),
 ("A chamber built for drowning divers was pointed at that question.", "flip", "body", "BUILT FOR DIVERS"),
 ("Tel Aviv, 2020. Doctor Shai Efrati takes thirty-five adults, all sixty-four or older.", "story", "body", "35 ADULTS. ALL OVER 64."),
 ("Sixty sessions in a pressurised chamber, over ninety days.", "story", "body", "60 SESSIONS IN 90 DAYS"),
 ("The chambers were designed for divers surfacing too fast, not for old age.", "story", "body", "NOT DESIGNED FOR AGE"),
 ("At the ends of your chromosomes sit caps called telomeres. They shorten each time a cell divides.", "story", "body", "CAPS THAT KEEP SHORTENING"),
 ("They are a clock. Everyone's runs one direction.", "story", "body", "A CLOCK THAT RUNS ONE WAY"),
 ("Blood taken after ninety days showed those caps longer by up to thirty-eight percent.", "story", "body", "LONGER BY 38%"),
 ("Worn-out cells that refuse to die dropped by up to thirty-seven percent.", "story", "body", "37% FEWER WORN-OUT CELLS"),
 ("Thirty-five people is a small room, and no one has yet shown it means a longer life.", "burial", "body", "THIRTY-FIVE IS A SMALL ROOM"),
 ("The oxygen is not the trick. Pressure then release is a controlled stress that makes cells repair.", "today", "body", "STRESS, THEN REPAIR"),
 ("It costs what a car costs, and nobody is giving it away, darling.", "today", "body", "IT COSTS WHAT A CAR COSTS"),
 ("The clock at the end of your chromosomes moved. That was thought impossible.", "identity", "closer", "THE CLOCK MOVED"),
])

S["the-chinese-herb-the-biotech-company-patented-in-the-year-20"] = dict(
title="The Root They Patented",
card="A THOUSAND-YEAR ROOT. PATENTED IN 2000.",
beats=[
 ("You feel old at a level no cream reaches, darling.", "pain", "hook", "DEEPER THAN ANY CREAM"),
 ("A California company went looking for that level in a Chinese apothecary.", "flip", "body", "THEY WENT LOOKING IN AN APOTHECARY"),
 ("The year 2000. Geron Corporation begins screening traditional Chinese medicine extracts.", "story", "body", "THE YEAR 2000"),
 ("They are hunting one thing: something that switches on telomerase.", "story", "body", "HUNTING ONE ENZYME"),
 ("Telomerase rebuilds the caps on your chromosomes that shorten every time a cell divides.", "story", "body", "IT REBUILDS THE CAPS"),
 ("They find it inside astragalus root, used in China for over a thousand years.", "story", "body", "INSIDE ASTRAGALUS ROOT"),
 ("The molecule is cycloastragenol. They patent it.", "story", "body", "THEY PATENTED IT"),
 ("From 2008 it sells as TA-65, at a price no herbalist ever charged.", "story", "body", "SOLD AS TA-65"),
 ("A thousand years in a clay pot, then a patent, then a price.", "burial", "body", "A PATENT, THEN A PRICE"),
 ("The same enzyme that keeps a cell young is the one cancer cells switch on to never die.", "burial", "body", "CANCER USES THE SAME SWITCH"),
 ("A randomised trial in 2024 found it did measurably lengthen telomeres in people over fifty.", "today", "body", "MEASURED IN 2024"),
 ("The root itself is still sold as tea and powder for almost nothing, darling.", "today", "body", "THE ROOT IS STILL CHEAP"),
 ("They did not discover it. They found it, and put a fence around it.", "identity", "closer", "THEY BUILT A FENCE"),
])

S["the-cuddle-hormone-that-rebuilt-old-muscle"] = dict(
title="The Hormone Of Being Held",
card="BERKELEY, 2014. OLD MUSCLE WOKE UP.",
beats=[
 ("A pulled muscle used to heal in a week and now it takes a season, darling.", "pain", "hook", "A WEEK, NOW A SEASON"),
 ("The reason may be a hormone you make when someone holds you.", "flip", "body", "MADE WHEN YOU ARE HELD"),
 ("Berkeley, 2014. Irina Conboy's lab, working with Christian Elabd and Wendy Cousin.", "story", "body", "BERKELEY, 2014"),
 ("They measured oxytocin in the blood of young mice and old mice.", "story", "body", "YOUNG BLOOD, OLD BLOOD"),
 ("Oxytocin is the bonding hormone. Childbirth, touch, trust.", "story", "body", "THE BONDING HORMONE"),
 ("Young mice carried roughly three times as much of it as the old ones.", "story", "body", "THREE TIMES AS MUCH"),
 ("So they injected the old mice with it and watched the muscle.", "story", "body", "THEY INJECTED THE OLD ONES"),
 ("The muscle stem cells started dividing and repairing like a young animal's again.", "story", "body", "OLD STEM CELLS WOKE UP"),
 ("Oxytocin receptors sit directly on muscle stem cells. Both the hormone and the receptors fall with age.", "burial", "body", "RECEPTORS SIT ON THE MUSCLE"),
 ("Nobody was looking there. It was filed under childbirth, not repair.", "burial", "body", "FILED UNDER CHILDBIRTH"),
 ("It was mice. Injecting yourself with oxytocin does not do this, and it is not sold for it.", "today", "body", "THIS WAS MICE"),
 ("But it names one quiet reason a tear heals fast at twenty-five and slow at fifty-five.", "today", "body", "FAST AT 25. SLOW AT 55."),
 ("The hormone of being held turned out to be the hormone of being rebuilt, darling.", "identity", "closer", "HELD, THEN REBUILT"),
])
