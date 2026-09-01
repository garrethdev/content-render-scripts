"""Podcast-clip render lane: ingest pool -> hook + face-aware PiP render -> Supabase.

Modules:
  config      env, paths, keys, models, render constants
  supa        Supabase REST client + domain ops (clips, renders, storage)
  openrouter  chat-completions client + JSON extraction
  media       yt-dlp download, ffprobe, frame sampling, manifest, filler_mover render
  hookscan    hook-vs-caption detection = Gemini reads overlay text + Whisper speech, deterministic compare (first 6s)
  hooks       Claude hook writing for clean clips
  classify    health/wellness/weightloss topic gate
  worker      per-clip orchestration + CLI
"""
