"""Topic gate: label podcast_clips.on_topic (health/wellness/weightloss vs off-topic) by title, batched."""
from . import config, supa, openrouter

_PROMPT = (
    "You gate podcast shorts for a HEALTH & WELLNESS brand (peptides, GLP-1, weight loss, fitness, "
    "nutrition, metabolic/hormonal health, sleep, longevity, mental health, medical). For each numbered "
    "title, is its PRIMARY focus health/wellness/weightloss/fitness/nutrition/medical/mental-health? "
    "Money, business, relationships, dating, marriage, celebrity gossip, aliens, politics = NOT on topic. "
    "Return ONLY a JSON object mapping index to true/false, e.g. {\"0\":true,\"1\":false}.\n\n")

def _classify_batch(batch):
    lines = "\n".join(f'{i}. [{c.get("show","")}] {c.get("title","")}' for i, c in enumerate(batch))
    reply = openrouter.chat(config.TOPIC_MODEL, [{"role": "user", "content": _PROMPT + lines}],
                            max_tokens=1500)
    return openrouter.extract_json(reply)

def run(batch_size=40):
    clips = supa.fetch_unclassified()
    print(f"to classify: {len(clips)}")
    on = off = 0
    for i in range(0, len(clips), batch_size):
        batch = clips[i:i + batch_size]
        try:
            res = _classify_batch(batch)
        except Exception as e:
            print("batch fail", e); continue
        for j, c in enumerate(batch):
            val = bool(res.get(str(j), False))
            supa.patch_clip(c["video_id"], {"on_topic": val})
            on += val; off += (not val)
        print(f"  {i+len(batch)}/{len(clips)} done (on={on} off={off})")
    print(f"DONE on_topic={on} off_topic={off}")

def main():
    run()

if __name__ == "__main__":
    main()
