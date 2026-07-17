#!/usr/bin/env bash
# Env bridge for running the repo render scripts locally.
# The repo copies read generic env var names (SUPABASE_URL, SUPABASE_ANON_KEY,
# SUPABASE_SERVICE_KEY, SCRAPECREATORS_KEY, OPENROUTER_KEY) that the original
# working-dir scripts had hardcoded. This maps the names already present in
# ~/.config/peptide-secrets/.env onto those. Non-destructive: only fills a
# var if it isn't already set, so a real SUPABASE_* in the environment wins.
#
# Also pulls the latest render scripts from GitHub before each render pass, so
# the repo clone is the source of truth (single-source render).

set -a
[ -f "$HOME/.config/peptide-secrets/.env" ] && . "$HOME/.config/peptide-secrets/.env"

: "${SUPABASE_URL:=https://qlcmgxgwpzmiebzxflai.supabase.co}"
: "${SUPABASE_ANON_KEY:=${CAROUSEL_SUPABASE_PUBLISHABLE_KEY}}"
: "${SUPABASE_PUBLISHABLE_KEY:=${CAROUSEL_SUPABASE_PUBLISHABLE_KEY}}"
: "${SUPABASE_SERVICE_KEY:=${CAROUSEL_SUPABASE_SECRET_KEY}}"
: "${SCRAPECREATORS_KEY:=${SCRAPECREATORS_API_KEY}}"
: "${OPENROUTER_KEY:=${OPENROUTER_API_KEY}}"
set +a

# Pull latest render scripts (fast no-op when already current; never blocks a render).
git -C "$HOME/Claude/peptide-renderers" pull --quiet --ff-only 2>/dev/null || true
