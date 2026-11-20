-- 20261119_wire_camera_roll_story.sql
-- Wires the Camera Roll Story lane (Character 6, eight slide image carousel).
-- Follows "Wiring a new carousel content type" (https://claude.ai/artifact/XUj99rfkXJfy4HMzCYtLp2), steps 1 to 6.
-- Garreth's answers, 2026-11-19: name Camera Roll Story, cadence 0 for now (so no sister lane changes and
-- Character 6 stays at 18 of 18), table open to the public key like Divorce Recovery.
-- Proven in a rolled-back run before it was applied. Not in this file: the Smart Scheduler MEDIA entry and the
-- nightly gate filter (n8n, by hand), captions, music and the content check.

-- ---------------------------------------------------------------- 0. the table (handover section 1)
create sequence if not exists public.camera_roll_story_carousel_seq;

create table public.camera_roll_story_carousel (
  id uuid primary key default gen_random_uuid(),
  carousel_id text unique not null
    default ('CRS-' || lpad(nextval('camera_roll_story_carousel_seq')::text, 4, '0')),
  content_id text generated always as (carousel_id) stored,
  batch text,
  "character" text default 'Character 6',
  pillar text default 'camera_roll_story',
  deck jsonb,                 -- the writer's full output: story plan, hook candidates, shots, source post
  source_url text,            -- the real post the story was retold from
  hook_text text,
  slide_1 text, slide_2 text, slide_3 text, slide_4 text,
  slide_5 text, slide_6 text, slide_7 text, slide_8 text,
  slide_1_url text, slide_2_url text, slide_3_url text, slide_4_url text,
  slide_5_url text, slide_6_url text, slide_7_url text, slide_8_url text,
  source_images jsonb,        -- the renderer's picks, so a re-render keeps the same pictures
  caption text,
  music text,
  status text default 'scripted',
  render_status text default 'pending',
  render_error text,
  rendered_at timestamptz,
  render_set text,
  risk_flag text,
  writer_problems jsonb,
  gatekeep_status text, gatekeep_notes text, gatekeep_reviewed_at timestamptz,
  quality_status text, quality_score integer, quality_notes text, quality_reviewed_at timestamptz,
  scheduler_ready boolean,
  geelark_profile text,
  platform text,
  posting_date timestamptz,
  posting_time time,
  posting_status text,        -- must start NULL for the scheduler; 'Hold' is the only manual hold
  scheduled_at timestamptz,
  geelark_task_id text,
  notion_page_id text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
alter table public.camera_roll_story_carousel enable row level security;
-- Access: open with the public key, the same three rules divorce_recovery_carousel has (Garreth, 2026-11-19).
create policy "anon select camera_roll_story_carousel" on public.camera_roll_story_carousel for select to anon using (true);
create policy "anon insert camera_roll_story_carousel" on public.camera_roll_story_carousel for insert to anon with check (true);
create policy "anon update camera_roll_story_carousel" on public.camera_roll_story_carousel for update to anon using (true) with check (true);

create trigger set_updated_at_camera_roll_story_carousel
before update on public.camera_roll_story_carousel
for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- 1. content-type list row
insert into content_type_registry (
  content_type, display_name, source_table, source_id_column,
  source_profile_column, source_date_column, source_time_column,
  "character", quota_bucket, media_shape, needs_music, has_baked_audio,
  ig_endpoint, ig_params, tt_task_type, tt_params,
  cadence_per_week, cadence_ceiling_per_week,
  day_pattern, time_window_start, time_window_end,
  min_gap_minutes, max_posts_per_day, low_inventory_threshold_days,
  alert_min_posts, alert_window_days,
  active, unified_poster_active, lifecycle, lifecycle_note, audit_fields
) values (
  'camera_roll_story', 'Camera Roll Story Carousel', 'camera_roll_story_carousel', 'carousel_id',
  'geelark_profile', 'posting_date', 'posting_time',
  'Character 6', 'glp', 'image_carousel', true, false,
  'instagramPubReelsImages', '{"publishPost":false}'::jsonb, 3, '{"sameVideoVolume":100}'::jsonb,
  0, 7,
  'every_day', '11:00:00', '22:15:00',
  120, 1, 3,
  3, 7,
  true, true, 'live', '2026-11-19: wired at cadence 0, so nothing is scheduled until a cadence is set. Renderer renderers/camera_roll_story.',
  '{"caption":["caption"],"text_hook":["hook_text"],"transcript":[],
    "on_screen_text":["slide_1","slide_2","slide_3","slide_4","slide_5","slide_6","slide_7","slide_8"]}'::jsonb
);
-- Timing note from the handover doc: a new type gets every account's first slot for 7 days, and loses
-- that week if its decks arrive more than 30 days after this row is made. Run this file when decks are close.

-- ---------------------------------------------------------------- 2. the character's allowed list
update characters
set allowed_content_types = array_append(allowed_content_types, 'camera_roll_story'), updated_at = now()
where "character" = 'Character 6' and not (allowed_content_types @> array['camera_roll_story']);

-- ---------------------------------------------------------------- 3. weekly mix
-- Nothing to change: the lane starts at cadence 0, so Character 6 still adds up to 18.

-- ---------------------------------------------------------------- 4. the ready switch (all eight slides)
create or replace function public.trg_sr_camera_roll_story_carousel()
returns trigger language plpgsql as $function$
begin
  if coalesce(new.posting_status, '') <> 'Hold'
     and new.gatekeep_status = 'approved'
     and coalesce(new.quality_status, '') <> 'poor'
     and new.slide_1_url is not null and new.slide_2_url is not null
     and new.slide_3_url is not null and new.slide_4_url is not null
     and new.slide_5_url is not null and new.slide_6_url is not null
     and new.slide_7_url is not null and new.slide_8_url is not null
     and new.render_status = 'rendered'
     and new.scheduler_ready is not true
     and new.caption is not null
  then new.scheduler_ready := true; end if;
  return new;
end $function$;

create trigger sr_autoset_camera_roll_story_carousel
before insert or update on public.camera_roll_story_carousel
for each row execute function public.trg_sr_camera_roll_story_carousel();

-- ---------------------------------------------------------------- 5. the posting view (append, never retype)
do $$
declare v text;
begin
  select pg_get_viewdef('public.unified_posts'::regclass, true) into v;
  v := rtrim(v, E'; \n');
  if v ilike '%''camera_roll_story''::text AS content_type%' then raise notice 'already present'; return; end if;
  v := v || E'\nUNION ALL\n SELECT ''camera_roll_story''::text AS content_type,\n'
    || E'    t.carousel_id AS content_id,\n    t.geelark_profile,\n'
    || E'    lower(COALESCE(t.platform, ''''::text)) AS platform,\n'
    || E'    t.posting_date,\n    (t.posting_time)::text AS posting_time,\n    t.posting_status,\n'
    || E'    NULL::text AS media_url,\n'
    || E'    array_remove(ARRAY[t.slide_1_url, t.slide_2_url, t.slide_3_url, t.slide_4_url, t.slide_5_url, t.slide_6_url, t.slide_7_url, t.slide_8_url], NULL::text) AS media_urls,\n'
    || E'    t.caption,\n    t.music AS music_label\n'
    || E'   FROM camera_roll_story_carousel t\n  WHERE (t.render_status = ''rendered''::text)';
  execute 'create or replace view public.unified_posts as ' || v;
end $$;
-- Checked 2026-11-19: unified_posts has these eleven columns in this order, the same as the Divorce Recovery branch.

-- ---------------------------------------------------------------- 6. the stock view (cached copy)
-- cache.v_scheduler_pool is a materialized view and public.v_scheduler_pool is a view over it (plus the
-- Comparison branch). Recipe from the handover doc: build a new copy with the extra branch, index it, point the
-- public view at it, drop the old copy, rename. Both definitions are read live, nothing is retyped.
do $$
declare c text; p text;
begin
  select rtrim(pg_get_viewdef('cache.v_scheduler_pool'::regclass, true), E'; \n') into c;
  if c ilike '%''camera_roll_story''::text AS content_type%' then raise notice 'already present'; return; end if;
  c := c || E'\nUNION ALL\n SELECT ''camera_roll_story''::text AS content_type,\n'
    || E'    ''Character 6''::text AS "character",\n    ''glp''::text AS bucket,\n    count(*) AS pool_n\n'
    || E'   FROM camera_roll_story_carousel t\n'
    || E'  WHERE COALESCE(t.posting_status, ''''::text) = ''''::text AND t.geelark_profile IS NULL AND t.scheduler_ready'
    || E' AND t.gatekeep_status = ''approved''::text AND COALESCE(t.quality_status, ''''::text) <> ''poor''::text'
    || E' AND t.slide_1_url IS NOT NULL AND t.caption IS NOT NULL';
  execute 'create materialized view cache.v_scheduler_pool_new as ' || c;
  execute 'create unique index v_scheduler_pool_key_new on cache.v_scheduler_pool_new (content_type, "character", bucket)';
  select rtrim(pg_get_viewdef('public.v_scheduler_pool'::regclass, true), E'; \n') into p;
  if position('FROM cache.v_scheduler_pool' in p) = 0 then raise exception 'public.v_scheduler_pool no longer reads cache.v_scheduler_pool'; end if;
  p := replace(p, 'FROM cache.v_scheduler_pool', 'FROM cache.v_scheduler_pool_new v_scheduler_pool');
  execute 'create or replace view public.v_scheduler_pool as ' || p;
  execute 'drop materialized view cache.v_scheduler_pool';            -- no cascade: nothing else may depend on it
  execute 'alter materialized view cache.v_scheduler_pool_new rename to v_scheduler_pool';
  execute 'alter index cache.v_scheduler_pool_key_new rename to v_scheduler_pool_key';
end $$;
