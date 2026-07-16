#!/usr/bin/env bash
# Wire the no-secrets guard into this clone's git hooks. Run once per clone.
set -euo pipefail
cd "$(dirname "$0")/.."
for h in pre-commit pre-push; do
  ln -sf ../../scripts/no-secrets-check.sh ".git/hooks/$h"
  echo "installed $h -> scripts/no-secrets-check.sh"
done
