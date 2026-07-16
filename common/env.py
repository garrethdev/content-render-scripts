"""Shared secret + config loader for every renderer in this repo.

Rule for this repo: NEVER hardcode a key, URL-with-token, or absolute asset
path in a renderer. Read secrets through `require()` / `get()` here, and read
tunable paths through `get(NAME, default)`.

Load order (first value wins, via setdefault):
  1. process environment (already-exported vars)
  2. ~/.config/peptide-secrets/.env   (the canonical machine-local secrets file)
  3. <repo-root>/.env                 (optional, git-ignored)

So the scripts run unchanged on this Mac (they find peptide-secrets), and on any
other machine you just provide the same vars. See .env.example for the names.
"""
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CANONICAL = os.path.expanduser("~/.config/peptide-secrets/.env")
_REPO_ENV = os.path.join(_REPO_ROOT, ".env")


def _parse_into_environ(path):
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_env(*extra_paths):
    for p in (_CANONICAL, _REPO_ENV, *extra_paths):
        _parse_into_environ(p)


def require(name):
    load_env()
    v = os.environ.get(name)
    if not v:
        raise SystemExit(
            f"Missing required env var {name!r}. Set it in "
            f"~/.config/peptide-secrets/.env or {_REPO_ENV} (see .env.example)."
        )
    return v


def get(name, default=None):
    load_env()
    return os.environ.get(name, default)


# Load on import so `from common import env; env.get(...)` just works.
load_env()
