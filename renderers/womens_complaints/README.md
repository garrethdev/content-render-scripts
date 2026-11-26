# Women's Complaints renderer

Render agent for the `womens_complaints` lane (Character 6): eight slide carousels about one complaint, belly, upper arms or double chin. The table is `public.womens_complaints_carousel`, and the writer is the n8n workflow `OUNkXW14hBlslnDg`.

```
python3 render_womens_complaints.py --plan               # show the picture picks for pending rows
python3 render_womens_complaints.py --upload             # render pending rows, upload, mark rendered
python3 render_womens_complaints.py --carousel WC-0003 --all --repick --upload
```

## Pictures (Garreth, 2026-11-25)

- **Slide 1:** one of his approved complaint photos. They are stored in `rich-life-images/womens-complaints/complaint-photos/`. The hook is placed away from the body part.
- **Slides 2 to 6:** nature or food only, with no photo of her and no hands. They alternate nature and food, starting at random. (Garreth, 2026-11-25: "remove as many images of her in the middle slides and tell the renderer to balance out more just nature or food shots".) Nature comes from `character-6/nature-basis/` plus older no-person scenery. Food comes from `character-6/food-basis/` plus older no-person food shots.
- **Slides 7 and 8 (the reveal):** photos tagged "after" **and** "old".

The tags come fresh on every run from `public.v_character6_picture_pool`. That view holds the active `jealousy_image_pool` rows under `rich-life-images/character-6/` whose file still exists in storage. No picture repeats inside a deck.

The text is the shared Character 6 look from the Camera Roll Story renderer, and it is never tilted.

## Keys

`SUPABASE_ANON_KEY` is enough. The table, the view and both storage folders are open to it.

## Output

Slides go to `rich-life-images/womens-complaints/renders/<carousel_id>/slide_0N.jpg`. Each row gets `slide_N_url`, `source_images` (the picks) and `render_status = 'rendered'`.
