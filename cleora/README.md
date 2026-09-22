# Cleora render scripts

Director, shot-librarian, QA, TTS-prep and OpenMontage render wrappers for the Madame Cleora pipeline.

- `director/` — clip casting (`cast.py`), the Director system prompt, and `shot_librarian.py`
  (generates + tags missing claymation shots and adds them to the `cleora_clips` library).
- `hooks/` — original OpenMontage episode builders (`build_episode.py`, `build_new_episode.py`, `hook_card.py`).
- `mac/` — the macOS-adapted builders actually used on this machine (paths repointed, ElevenLabs
  isolation disabled for synthetic TTS, music optional/voice-only, env-driven low-res via `CLEORA_W`/`CLEORA_H`).
- `qa/ slate/ scripts/ sfx/ captions/` — QA gate, TTS/slate helpers, batch scripts, SFX, captions.

Secrets are NOT committed (see `.gitignore`). Note: some scripts still carry inline Supabase
publishable/anon keys — scrub these to env vars before any public push.
