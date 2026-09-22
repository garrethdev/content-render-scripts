import qa
lib  = qa.get("cleora_clips?status=eq.active&select=shot_key,vo_safe,talk_capable,can_open")
rows = qa.get("cleora_content?content_id=like.CLE-B6-*&script_status=eq.scripted"
              "&select=content_id,title,script,edl")
rows = sorted(rows, key=lambda r: r['content_id'])
fails=warns=clean=0; report=[]
for r in rows:
    fs = qa.check_episode(r, lib)
    b=[x for x in fs if x.blocking]; w=[x for x in fs if not x.blocking]
    if b: fails+=1
    elif w: warns+=1
    else: clean+=1
    if b or w: report.append((r['content_id'], b, w))
print(f"\n=== b6 QA gate: {len(rows)} episodes | {clean} clean, {warns} warn-only, {fails} FAIL ===")
for cid,b,w in report:
    print(cid, f"({len(b)} blocking, {len(w)} warn)")
    for x in b+w: print("   ", str(x).strip())
