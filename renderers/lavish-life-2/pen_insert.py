#!/usr/bin/env python3
"""Surgical pen insertion into approved keeper images."""
import fal_client, os, json, sys, urllib.request
items = json.load(open(sys.argv[1]))
OUT = "out/pen_inserts"; os.makedirs(OUT, exist_ok=True)
for it in items:
    src_url = fal_client.upload_file(os.path.expanduser(it["src"]))
    for attempt in range(3):
        try:
            res = fal_client.subscribe("fal-ai/gpt-image-2/edit",
                arguments={"prompt": it["prompt"], "image_urls": [src_url],
                           "num_images": 1, "image_size": "portrait_16_9"})
            urllib.request.urlretrieve(res["images"][0]["url"], f"{OUT}/{it['id']}.jpg")
            print("OK", it["id"]); break
        except Exception as e:
            print("err", it["id"], str(e)[:90])
