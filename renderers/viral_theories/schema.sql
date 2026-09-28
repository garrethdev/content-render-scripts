-- viral_theories_carousel: applied to Supabase qlcmgxgwpzmiebzxflai on 2026-09-28
-- (migration "create_viral_theories_carousel"). Kept here for reference/rebuilds.
create table public.viral_theories_carousel (
  id uuid primary key default gen_random_uuid(),
  carousel_id text not null unique,
  pillar text not null default 'viral_theories',
  angle text,
  character text not null default 'Character 6',
  hook_type text not null default 'viral_theories',
  hook_text text,
  slots jsonb not null,
  slide_1 text, slide_2 text, slide_3 text, slide_4 text, slide_5 text, slide_6 text,
  slide_1_url text, slide_2_url text, slide_3_url text, slide_4_url text, slide_5_url text, slide_6_url text,
  source_images jsonb,
  brand text,
  caption text,
  music text,
  status text not null default 'scripted',
  approved boolean not null default false,
  approved_at timestamptz,
  vote text,
  voted_at timestamptz,
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

comment on table public.viral_theories_carousel is
  '"5 viral theories" 6-slide carousel. slots = writer JSON {angle, hook_lines[4], hook_sub[2], theories[5]{title,body_1,body_2}, plug_theory, caption}; renderer reads slots, writes slide_N_url (final renders) + source_images {"1".."6": source url}.';

create trigger set_updated_at_viral_theories_carousel
  before update on public.viral_theories_carousel
  for each row execute function public.set_updated_at();

create index viral_theories_carousel_render_queue_idx
  on public.viral_theories_carousel (approved, rendered_at);

alter table public.viral_theories_carousel enable row level security;
