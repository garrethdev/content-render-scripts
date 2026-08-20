#!/usr/bin/env python3
"""Re-judge only the rows in recheck.json with the corrected prompt, merge into qa_results.json."""
import os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import qa_batch as Q
names=json.load(open('recheck.json'))
res=json.load(open('qa_results.json'))
print(f"[requa] {len(names)} videos")
def one(n):
    return n, Q.ask(os.path.join('renders', n))
with ThreadPoolExecutor(max_workers=5) as ex:
    for f in as_completed([ex.submit(one,n) for n in names]):
        try: n,v=f.result()
        except Exception as e: continue
        res[n]=v
        print(f"  {v.get('verdict','?'):5} {n}  {v.get('reason','')}")
json.dump(res, open('qa_results.json','w'), indent=1)
import collections
c=collections.Counter(v.get('verdict','?') for v in res.values())
print(f"\n[requa] final {len(res)} judged: {dict(c)}")
