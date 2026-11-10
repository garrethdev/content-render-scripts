-- public.journey_3slide_carousel (project qlcmgxgwpzmiebzxflai) -- as applied 2026-09-30.
-- Modeled on covered_eye_carousel. 3 slides: Character 6 BEFORE + hook / constant
-- "Directed by Robert B. Weide" card / Character 6 AFTER.
create table public.journey_3slide_carousel (
  id uuid primary key default gen_random_uuid(),
  carousel_id text unique,
  character text not null default 'Character 6',
  pillar text default 'journey_3slide',
  hook_type text,
  hook_text text,                 -- slide 1 overlay: variations of "I'm gonna lose some weight"
  hook_center_x numeric default 540,   -- per-row hook position (from the Figma samples)
  hook_top_y numeric default 1000,
  before_image_url text,          -- rich-life-images/character-6/before-basis/...
  after_image_url text,           -- rich-life-images/character-6/carousel-basis/...
  slide_2_source_url text,        -- optional override of the constant slide 2
  slide_1_url text, slide_2_url text, slide_3_url text,
  caption text, music text,
  status text default 'pending_review',
  approved boolean default false, approved_at timestamptz,
  vote text, voted_at timestamptz,
  batch text, render_set text,
  render_status text default 'pending',
  gatekeep_status text, gatekeep_notes text, gatekeep_reviewed_at timestamptz,
  quality_score integer, quality_status text, quality_notes text, quality_reviewed_at timestamptz,
  rendered_at timestamptz, scheduled_at timestamptz,
  geelark_profile text, platform text,
  posting_date timestamptz, posting_time time, posting_status text,
  geelark_task_id text, notion_page_id text,
  created_at timestamptz default now(),
  scheduler_ready boolean not null default false,
  updated_at timestamptz default now()
);
create index idx_journey_3slide_carousel_status on public.journey_3slide_carousel (status);
create index idx_journey_3slide_carousel_batch on public.journey_3slide_carousel (batch);
create trigger set_updated_at_journey_3slide_carousel before update on public.journey_3slide_carousel
  for each row execute function public.set_updated_at();

-- scheduler_ready trigger doubles as the media guard: needs all 3 rendered slides
create or replace function public.trg_sr_journey_3slide_carousel() returns trigger language plpgsql as $f$
begin
  if coalesce(new.posting_status,'') <> 'Hold' and new.gatekeep_status = 'approved'
     and coalesce(new.quality_status,'') <> 'poor'
     and new.slide_1_url is not null and new.slide_2_url is not null and new.slide_3_url is not null
     and new.render_status = 'rendered' and new.scheduler_ready is not true and new.caption is not null
  then new.scheduler_ready := true; end if;
  return new;
end $f$;
create trigger sr_autoset_journey_3slide_carousel before insert or update on public.journey_3slide_carousel
  for each row execute function public.trg_sr_journey_3slide_carousel();
