#!/usr/bin/env python3
"""The worker. Leave it running (computer on); it pulls jobs from Supabase, renders them
locally with ffmpeg in small batches, uploads each finished MP4 back to Supabase, and marks
each row done — committing one at a time so a crash only loses the in-flight video.

Job queue (in viral_filler_content.status):
  queued  -> claimed by worker -> rendering -> done (render_url set)  |  failed
"""
import time, traceback
import config, supa, render, thumbs

def claim_batch():
    rows = supa.rest(f"viral_filler_content?status=eq.{config.QUEUE_STATUS}"
                     f"&select=id,filler_aweme_id,source_url,character_url,character_id,hook,treatment"
                     f"&order=created_at.asc&limit={config.BATCH}") or []
    claimed = []
    for r in rows:
        # version guard: never render a job whose treatment this worker can't do -> leave it
        # queued for an updated worker (both machines must pull before new treatments go live).
        if not render.treatment_known(r.get("treatment")):
            print(f"  skip row {r['id']}: unknown treatment {r.get('treatment')!r} (needs newer worker)")
            continue
        # optimistic claim: only succeeds if still queued (filter guards against another worker)
        res = supa.rest(f"viral_filler_content?id=eq.{r['id']}&status=eq.{config.QUEUE_STATUS}",
                        "PATCH", {"status": "rendering"}, prefer="return=representation")
        if res:
            claimed.append(r)
    return claimed

def queue_depth():
    rows = supa.rest(f"viral_filler_content?status=eq.{config.QUEUE_STATUS}&select=id") or []
    return len(rows)

def run_batch(fire_captions=True):
    batch = claim_batch()
    if not batch:
        return 0, 0
    print(f"[batch] claimed {len(batch)} job(s)")
    done = failed = 0
    for r in batch:
        try:
            mp4 = render.render_job(r)
            with open(mp4, "rb") as f:
                url = supa.upload(f"renders/{r['id']}.mp4", f.read(), "video/mp4")
            supa.rest(f"viral_filler_content?id=eq.{r['id']}", "PATCH",
                      {"render_url": url, "status": "done"}, prefer="return=minimal")
            done += 1
            print(f"  done  row {r['id']} -> {url}")
        except Exception as e:
            supa.rest(f"viral_filler_content?id=eq.{r['id']}", "PATCH",
                      {"status": "failed"}, prefer="return=minimal")
            failed += 1
            print(f"  FAIL  row {r['id']}: {e}")
            traceback.print_exc()
    # fill captions for whatever just rendered (the live Universal Caption Maker writes them back)
    if done and fire_captions:
        try:
            render.trigger_captions()
        except Exception as e:
            print("  caption trigger failed:", e)
    print(f"[batch] {done} done, {failed} failed, {queue_depth()} still queued")
    return done, failed

def main():
    print(f"viral-content-filler worker up. polling status='{config.QUEUE_STATUS}' "
          f"(batch={config.BATCH}, poll={config.POLL_SECONDS}s). ctrl-c to stop.")
    last_thumb = 0.0
    while True:
        try:
            done, failed = run_batch()
        except Exception as e:
            print("worker loop error:", e); time.sleep(config.POLL_SECONDS); continue
        if done == 0 and failed == 0:
            # idle: spend the cycle giving newly-ingested clips a preview thumbnail.
            # No-op when nothing's missing; throttled so it scans at most every few minutes.
            now = time.monotonic()
            if now - last_thumb >= config.THUMB_EVERY_SECONDS:
                last_thumb = now
                try:
                    ok, tfail = thumbs.fill_missing()
                    if ok or tfail:
                        print(f"[thumbs] filled {ok}, failed {tfail}")
                except Exception as e:
                    print("thumb fill error:", e)
            time.sleep(config.POLL_SECONDS)

if __name__ == "__main__":
    main()
