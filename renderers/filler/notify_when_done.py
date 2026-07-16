#!/usr/bin/env python3
"""Watch the render queue; when it's empty, email a summary via the n8n Gmail webhook.
Runs independently of any chat session. Also exits (and emails) if rendering stalls or after 4h.
"""
import urllib.request, json, time, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common import env

SB = env.get("SUPABASE_URL", "https://qlcmgxgwpzmiebzxflai.supabase.co") + "/rest/v1"
ANON = env.require("SUPABASE_ANON_KEY")
H = {"apikey": ANON, "Authorization": "Bearer " + ANON}
EMAIL_HOOK = "https://czed.app.n8n.cloud/webhook/11647f73-bbf8-403b-ba97-8784c36d8e19"
RECIPIENTS = ["garrethdottin@gmail.com", "czedrickjhake.cc@gmail.com"]
BASELINE_DONE = 537   # finished count before this render run started

def cnt(status):
    req = urllib.request.Request(SB + f"/viral_filler_content?status=eq.{status}&select=id", headers=H)
    return len(json.load(urllib.request.urlopen(req, timeout=30)))

def main():
    start = time.time(); last_done = -1; stall = 0; reason = "complete"
    while True:
        try:
            q, r, d = cnt("queued"), cnt("rendering"), cnt("done")
        except Exception:
            time.sleep(120); continue
        if q == 0 and r == 0:
            reason = "complete"; break
        stall = stall + 1 if d == last_done else 0
        last_done = d
        if stall >= 20:                      # ~40 min with no progress
            reason = "stalled (workers may have stopped)"; break
        if time.time() - start > 4 * 3600:   # 4h safety cap
            reason = "timed out after 4h"; break
        time.sleep(120)

    done, failed, queued, rendering = cnt("done"), cnt("failed"), cnt("queued"), cnt("rendering")
    made = done - BASELINE_DONE
    subject = f"Viral filler render {'complete' if reason == 'complete' else 'update'} — {made} new videos"
    html = (f"<h2>Viral filler render {reason}</h2>"
            f"<p><b>{made}</b> new videos rendered this run.</p>"
            f"<ul><li>Total finished: <b>{done}</b></li>"
            f"<li>Failed: {failed}</li>"
            f"<li>Still queued: {queued} &nbsp;|&nbsp; In progress: {rendering}</li></ul>"
            f"<p>All videos are saved in <b>Supabase storage</b> at "
            f"<code>viral-filler/renders/&lt;id&gt;.mp4</code> "
            f"(each viral_filler_content row's <code>render_url</code>).</p>")
    for to in RECIPIENTS:
        try:
            body = json.dumps({"to": to, "subject": subject, "message": html}).encode()
            urllib.request.urlopen(urllib.request.Request(EMAIL_HOOK, data=body, headers={"Content-Type": "application/json"}), timeout=60)
            print("emailed", to)
        except Exception as e:
            print("email FAILED", to, e)
    print("watcher exit:", reason, "| made:", made)


if __name__ == "__main__":
    main()
