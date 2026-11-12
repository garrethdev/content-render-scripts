-- divorce_recovery_carousel: applied to Supabase qlcmgxgwpzmiebzxflai on 2026-10-16
-- (migration "create_divorce_recovery_carousel"). Kept here for reference/rebuilds.
--
-- 2026-11-12, migration "divorce_recovery_carousel_up_to_9_slides": decks can have 6 to 9
-- slides. It added slide_7 to slide_9, slide_7_url to slide_9_url and slide_count, made the
-- scheduler trigger wait for every slide the deck has, and added the three new links to the
-- divorce_recovery branch of the unified_posts view. See the end of this file.
create sequence if not exists public.divorce_recovery_carousel_seq;

create table public.divorce_recovery_carousel (
  id uuid primary key default gen_random_uuid(),
  carousel_id text not null unique
    default 'DRC-' || lpad(nextval('public.divorce_recovery_carousel_seq')::text, 4, '0'),
  content_id text generated always as (carousel_id) stored,
  pillar text not null default 'divorce_recovery',
  character text not null default 'Character 6',
  deck jsonb not null,                 -- the writer's deck, as returned by the n8n writer
  hook_text text,                      -- slide 1
  slide_1 text, slide_2 text, slide_3 text, slide_4 text, slide_5 text, slide_6 text,
  sender_name text,                    -- slide 2: his name on the notification
  message_time text,                   -- slide 2: e.g. '9:47 PM', also drives the lock-screen clock
  his_text text,                       -- slide 2: the notification body
  slide_1_url text, slide_2_url text, slide_3_url text, slide_4_url text, slide_5_url text, slide_6_url text,
  source_images jsonb,                 -- {"1": cover url, "2": {"wallpaper","contact"}, "3".."6": source url}
  caption text,
  music text,                          -- 'Artist - Title' from music_library
  status text not null default 'scripted',
  render_status text not null default 'pending',   -- pending | rendered | failed | review
  render_error text,
  writer_problems jsonb,
  batch text,
  render_set text,
  risk_flag text,
  gatekeep_status text,
  gatekeep_notes text,
  gatekeep_reviewed_at timestamptz,
  quality_score integer,
  quality_status text,
  quality_notes text,
  quality_reviewed_at timestamptz,
  rendered_at timestamptz,
  scheduled_at timestamptz,
  scheduler_ready boolean,
  geelark_profile text,
  platform text,
  posting_date timestamptz,
  posting_time time,
  posting_status text,
  geelark_task_id text,
  notion_page_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.divorce_recovery_carousel is
  'Divorce Recovery 6-slide carousel (Character 6). deck = n8n writer output; '
  'renderers/divorce_recovery/render_divorce_recovery.py picks the images, renders, '
  'writes slide_N_url + source_images and render_status=rendered.';

create trigger set_updated_at_divorce_recovery_carousel
  before update on public.divorce_recovery_carousel
  for each row execute function public.set_updated_at();

create index divorce_recovery_carousel_render_queue_idx
  on public.divorce_recovery_carousel (render_status, created_at);

alter table public.divorce_recovery_carousel enable row level security;
create policy "anon select divorce_recovery_carousel" on public.divorce_recovery_carousel
  for select to anon using (true);
create policy "anon insert divorce_recovery_carousel" on public.divorce_recovery_carousel
  for insert to anon with check (true);
create policy "anon update divorce_recovery_carousel" on public.divorce_recovery_carousel
  for update to anon using (true) with check (true);
grant usage on sequence public.divorce_recovery_carousel_seq to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------------------
-- 2026-11-12: up to nine slides (migration "divorce_recovery_carousel_up_to_9_slides")
-- ---------------------------------------------------------------------------------------
alter table public.divorce_recovery_carousel
  add column if not exists slide_7 text,
  add column if not exists slide_8 text,
  add column if not exists slide_9 text,
  add column if not exists slide_7_url text,
  add column if not exists slide_8_url text,
  add column if not exists slide_9_url text,
  add column if not exists slide_count integer;   -- 6 to 9; null means the original six

-- Ready for the scheduler only when every slide the deck has is rendered.
create or replace function public.trg_sr_divorce_recovery_carousel()
 returns trigger
 language plpgsql
as $function$
begin
  if coalesce(new.posting_status, '') <> 'Hold'
     and new.gatekeep_status = 'approved'
     and coalesce(new.quality_status, '') <> 'poor'
     and new.slide_1_url is not null
     and new.slide_2_url is not null
     and new.slide_3_url is not null
     and new.slide_4_url is not null
     and new.slide_5_url is not null
     and new.slide_6_url is not null
     and (coalesce(new.slide_count, 6) < 7 or new.slide_7_url is not null)
     and (coalesce(new.slide_count, 6) < 8 or new.slide_8_url is not null)
     and (coalesce(new.slide_count, 6) < 9 or new.slide_9_url is not null)
     and new.render_status = 'rendered'
     and new.scheduler_ready is not true
     and new.caption is not null
  then new.scheduler_ready := true; end if;
  return new;
end $function$;

-- unified_posts (the view the posting agent reads): its divorce_recovery branch now lists
-- slide_1_url to slide_9_url in media_urls. The migration changed only that branch.
