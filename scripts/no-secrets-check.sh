#!/usr/bin/env bash
# Blocks any commit/push that contains credential-shaped content.
# Installed as .git/hooks/pre-commit and pre-push (see scripts/install-hooks.sh).
# Scans STAGED content (what would actually land in the commit), not the worktree.
set -euo pipefail

PAT='sb_secret_[A-Za-z0-9]{6}|sb_publishable_[A-Za-z0-9]{6}|sk-or-v1-[A-Za-z0-9]{6}|sk-ant-[A-Za-z0-9]{6}|eyJhbGciOiJ[A-Za-z0-9]|AIzaSy[A-Za-z0-9]{10}|ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9]|xox[bap]-[A-Za-z0-9]|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'

# allow the placeholder docs file
hits=$(git diff --cached -U0 | grep -E '^\+' | grep -vE '^\+\+\+' | grep -EIn "$PAT" || true)
staged_env=$(git diff --cached --name-only | grep -E '(^|/)\.env$' || true)

fail=0
if [ -n "$hits" ]; then
  echo "✖ no-secrets-check: credential-shaped content in staged changes:" >&2
  echo "$hits" | cut -c1-120 >&2
  fail=1
fi
if [ -n "$staged_env" ]; then
  echo "✖ no-secrets-check: refusing to commit a .env file: $staged_env" >&2
  fail=1
fi
if [ $fail -ne 0 ]; then
  echo "  Move the value to ~/.config/peptide-secrets/.env or the repo .env (git-ignored)," >&2
  echo "  load it via common/env.py, and re-stage. To bypass ONLY for a false positive:" >&2
  echo "  git commit --no-verify" >&2
  exit 1
fi
exit 0
