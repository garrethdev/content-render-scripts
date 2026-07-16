#!/usr/bin/env python3
"""v4 vintage style, two-line layout: DIVORCE HORROR / STORIES."""
import fal_client, os, urllib.request

OUT = os.path.expanduser("~/Claude/divorce-horror-stories/out")

PROMPT = ('Retro 1970s horror-comic title graphic on a solid black background. '
          'The text "DIVORCE HORROR STORIES" in faded hot pink dripping letters with subtle '
          'grainy halftone print texture inside the letterforms, drips running down like old '
          'poster ink. Text wraps across two stacked centered lines: "DIVORCE HORROR" on the '
          'first line, "STORIES" on the second line, both centered and filling most of the '
          'frame width. Distressed vintage print feel, no other elements.')

res = fal_client.subscribe("fal-ai/gpt-image-2",
    arguments={"prompt": PROMPT, "num_images": 1,
               "image_size": {"width": 1024, "height": 1536},
               "quality": "high"})
url = res["images"][0]["url"]
fn = os.path.join(OUT, "v4_twoline.png")
urllib.request.urlretrieve(url, fn)
print(f"OK {fn}")
