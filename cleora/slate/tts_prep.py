"""Prepare a Cleora script read for the Higgsfield seed_audio voice clone.

The clone reads digits unreliably (the Alice Ball hook came back with a hallucinated "Flash" before
"1915" and a 7-second crawl through "23-year-old"), so every number is spelled out the way she would
say it: 4-digit years as "nineteen fifteen", "1300s" as "thirteen hundreds", "1940s" as "nineteen
forties", "23-year-old" as "twenty three year old", plain numbers as words, "$484 million" as
"four hundred and eighty four million dollars", percentages as "thirty percent". Ellipses (held
silences) are kept. Usage: from tts_prep import spoken; spoken("In 1915, 23 people...")
"""
import re
from num2words import num2words

DECADES={'0':'hundreds','1':'tens','2':'twenties','3':'thirties','4':'forties','5':'fifties','6':'sixties','7':'seventies','8':'eighties','9':'nineties'}

def _year(y):
    y=int(y)
    if 1100<=y<=1999 or 2010<=y<=2099: return num2words(y, to='year')
    return num2words(y)

def _decade(m):
    y=m.group(1); d=y[2]
    if y.endswith('00'): return f"{num2words(int(y[:2]))} hundreds"
    return f"{num2words(int(y[:2]))} {DECADES[d]}"

def _money(m):
    n=m.group(1).replace(',',''); unit=(m.group(2) or '').lower()
    v=float(n) if '.' in n else int(n)
    words=num2words(v)
    return f"{words} {unit} dollars" if unit else f"{words} dollars"

def spoken(text):
    t=text
    t=t.replace('—',', ').replace('–',', ').replace('&',' and ')
    t=re.sub(r'\$([\d,]+(?:\.\d+)?)(?:\s*(million|billion|thousand))?\b', _money, t, flags=re.I)
    t=re.sub(r'£([\d,]+(?:\.\d+)?)(?:\s*(million|billion|thousand))?\b', lambda m: _money(m).replace(' dollars',' pounds'), t, flags=re.I)
    # DAY-MONTH before the year rule, or "2 June 1934" reads as the cardinal "two June".
    t=re.sub(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
             lambda m: f"the {num2words(int(m.group(1)), to='ordinal')} of {m.group(2)}", t)
    t=re.sub(r'\b(\d+)\s*[-\u2013]\s*(\d+)\s*%',
             lambda m: f"{num2words(int(m.group(1)))} to {num2words(int(m.group(2)))} percent", t)
    # NUMBER RANGES ("60-120 mg", "20-40") before the plain-number rule, which otherwise glues the two
    # ends into one nonsense number ("sixty-one hundred and twenty mg").
    t=re.sub(r'\b(\d+)\s*[-\u2013]\s*(\d+)\b(?!\s*(?:year-old))',
             lambda m: f"{num2words(int(m.group(1)))} to {num2words(int(m.group(2)))}", t)
    # DECIMALS before any whole-number rule, or "0.2%" comes out as "zero.two percent".
    t=re.sub(r'\b(\d+)\.(\d+)\s*%', lambda m: f"{num2words(int(m.group(1)))} point "
             f"{' '.join(num2words(int(d)) for d in m.group(2))} percent", t)
    t=re.sub(r'\b(\d+)\.(\d+)\b', lambda m: f"{num2words(int(m.group(1)))} point "
             f"{' '.join(num2words(int(d)) for d in m.group(2))}", t)
    # ACRONYM+DIGIT (PDE5, COX2): the clone runs the letters and the digit together into a non-word.
    t=re.sub(r'\b([A-Z]{2,6})(\d{1,2})\b',
             lambda m: f"{' '.join(m.group(1))} {num2words(int(m.group(2)))}", t)
    t=re.sub(r'\b(1[1-9]\d\d|20\d\d)s\b', _decade, t)                       # 1300s, 1940s
    t=re.sub(r'\b(1[1-9]\d\d|20\d\d)\b', lambda m: _year(m.group(1)), t)      # years
    t=re.sub(r'(\d+)\s*%', lambda m: f"{num2words(int(m.group(1)))} percent", t)
    t=re.sub(r'(\d+)-year-old', lambda m: f"{num2words(int(m.group(1)))} year old", t)
    t=re.sub(r'\b(\d{1,3}(?:,\d{3})+)\b', lambda m: num2words(int(m.group(1).replace(',',''))), t)  # 100,000
    t=re.sub(r'\b(\d+)(st|nd|rd|th)\b', lambda m: num2words(int(m.group(1)), to='ordinal'), t)
    t=re.sub(r'\b(\d+)\b', lambda m: num2words(int(m.group(1))), t)
    t=re.sub(r'\s+',' ',t).strip()
    return t

if __name__=='__main__':
    import sys
    print(spoken(sys.stdin.read() if len(sys.argv)<2 else ' '.join(sys.argv[1:])))
