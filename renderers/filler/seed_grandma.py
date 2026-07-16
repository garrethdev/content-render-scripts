#!/usr/bin/env python3
"""Insert the 50 Grandma before/after hook pairs into grandma_before_after with clips assigned,
ready for render_ba.py batch. REST/JSON insert (no SQL escaping)."""
import json, urllib.request
import config
SB, KEY = config.SUPABASE_URL, config.SERVICE_KEY
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"}

PAIRS = [
 ("I stopped buying anything that had to zip.", "Bought jeans today in a number I have not seen since my thirties."),
 ("I used to hide in the back of every family photo.", "Now I am the one pulling everybody in close for it."),
 ("My husband used to look right past me at dinner.", "Last night he kept losing his place mid sentence."),
 ("I learned to get dressed without looking down.", "This morning I stood at the mirror longer than I needed to."),
 ("I saw my ex coming and ducked down an aisle.", "This time I said hello first and watched him fumble it."),
 ("My doctor said the numbers were just what fifty looks like.", "Last week she asked me to write down exactly what I changed."),
 ("I used to rest halfway up my own staircase.", "Now I carry the laundry up without thinking about it."),
 ("I almost skipped my class reunion altogether.", "I walked in and a woman asked who I came with."),
 ("I planned to wear black to my niece wedding and disappear.", "I wore deep green and three people asked where I got it."),
 ("I had not worn a swimsuit in public in fifteen years.", "I walked the whole beach in it and never reached for a towel."),
 ("My heels sat in the closet collecting dust.", "I wore them out and remembered how I used to walk."),
 ("I told my friend I was done dating at my age.", "I have two dinners this week and I picked the dress already."),
 ("The boy I liked in high school never noticed me.", "He found me online and asked if I was free Friday."),
 ("A younger woman called me ma'am like it was an insult.", "Now she asks me where I get my energy."),
 ("My sister said comfort was all we get after sixty.", "She borrowed my dress for her own anniversary dinner."),
 ("I used to volunteer to stay back from the office party.", "This year I closed the dance floor down."),
 ("I sat in the last pew so no one would look.", "Sunday I walked in late and the whole row turned."),
 ("The dressing room mirror used to end my whole day.", "Today I tried on the size below just for fun."),
 ("That leather jacket hung in my closet like a dare.", "It buttons now, and I have not taken it off all week."),
 ("Men used to look straight through me at the counter.", "Now they find a reason to keep the conversation going."),
 ("My daughter stopped suggesting we shop together.", "Saturday she asked to borrow my top."),
 ("I flinched when strangers looked too long.", "A woman stopped me downtown just to say I looked incredible."),
 ("I used to hold up the wall at every party.", "Last weekend I did not sit down once."),
 ("I canceled the cruise twice so I would not be in the photos.", "I booked the next one and packed two swimsuits."),
 ("I kept my scale in the closet and never looked.", "Now I check it like good news."),
 ("The kitchen called my name from the second I woke up.", "That noise went quiet, and I barely think about food now."),
 ("I used to need a nap by two every afternoon.", "Now I am the last one with the lights still on."),
 ("My knees made getting off the floor a whole event.", "I got up from the rug like it was nothing."),
 ("My belt only knew one notch for a decade.", "I am three holes in and had to buy a smaller one."),
 ("Nothing in the lingerie drawer fit the way it should.", "I bought something new and left the light on."),
 ("There is a red dress I hung up and gave up on.", "I wore it to dinner and a stranger sent over dessert."),
 ("My neighbor used to wave and keep walking.", "Now he slows down and forgets what he came outside for."),
 ("I kept my camera off on every video call.", "I turn it on first now and let them look."),
 ("My profile picture was eight years and forty pounds old.", "I posted a new one and my phone has not stopped."),
 ("I dreaded every birthday like it took something from me.", "I threw myself a party this year and wore the short dress."),
 ("I quit the class because I felt like the before picture.", "I went back and the instructor uses me as the example."),
 ("My friend stopped trying to set me up years ago.", "She called to say her husband friend would not stop asking."),
 ("A coworker walked right past me at the reunion lunch.", "He came back twice to be sure it was really me."),
 ("I used to ask for the table, never the booth.", "I slid into the booth this time without a second thought."),
 ("I wore a cover-up over my cover-up at the pool.", "This summer I left both at home."),
 ("I avoided my reflection in every store window.", "Now I catch it on purpose and keep walking."),
 ("My husband friends used to look past me too.", "One pulled him aside to ask what I had been doing."),
 ("We skipped photos at our anniversary for years.", "This year I asked the waiter to take twenty."),
 ("When a slow song played I always found the bathroom.", "Saturday my husband had to wait his turn to dance with me."),
 ("My doctor kept adding pills every single visit.", "This visit she took two of them away."),
 ("A man half my age held the elevator and I assumed it was manners.", "Turns out he just wanted to keep talking."),
 ("I used to fold myself small in every chair.", "Now I sit up like the room is mine."),
 ("I packed away every sundress I owned.", "I wore one downtown and felt the whole street notice."),
 ("I keep one old picture to remember who I was hiding.", "I keep the new one out where everyone can see."),
 ("I used to slip into rooms hoping no one looked up.", "Now I take my time, and they always do."),
]

BEFORE = ["Before_grandma_character_4_2-1-AfterEffects_iphone.mp4","Before_grandma_character_4_2-2-AfterEffects_iphone.mp4",
 "Before_grandma_character_4_4_iphone.mp4","Before_grandma_character_4_6-AfterEffects_iphone.mp4","Before_grandma_character_4_7-AfterEffects.mp4",
 "Before_grandma_character_4_8-2-AfterEffects_iphone.mp4","Before_grandma_character_4_8-2-long-shot.mp4","Before_grandma_character_4_8.mp4","Before_grandma_character_4_9.mp4"]
AFTER = ["After_grandma_character_4_1-1.mp4","After_grandma_character_4_2-1.mp4","After_grandma_character_4_2.mp4","After_grandma_character_4_3.mp4",
 "After_grandma_character_4_4-1.mp4","After_grandma_character_4_5-1-long-shot.mp4","After_grandma_character_4_5-2.mp4","After_grandma_character_4_6-2.mp4"]

rows = []
for i,(th,tha) in enumerate(PAIRS):
    rows.append({"carousel_id":"GBAF-%03d"%(i+1),"text_hook":th,"text_hook_after":tha,
        "before_clip":BEFORE[i%len(BEFORE)],"after_clip":AFTER[(i*3)%len(AFTER)],
        "before_trim_in":0,"before_trim_out":8,"after_trim_in":0,"after_trim_out":8,
        "audit_status":"approved","stitch_status":"ready"})
req = urllib.request.Request(SB+"/rest/v1/grandma_before_after", data=json.dumps(rows).encode(), method="POST", headers=H)
try:
    urllib.request.urlopen(req, timeout=120)
    print("inserted", len(rows), "rows (GBAF-001..050)")
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:600])
