#!/bin/bash
# Install the Argos Translate models AX-NEWS translates with (every language
# in backend/translation.py LANG_MAP, into English), under the HOME the
# backend and the translation worker use (backend/.env, HOME=...).
#
#   sudo -u cbrain deploy/install-argos-models.sh            # all of them
#   sudo -u cbrain deploy/install-argos-models.sh tr fr      # some of them
#
# About 2.5 GB in all; each model is downloaded once, then works offline.
set -euo pipefail
APP=$(cd "$(dirname "$0")/.." && pwd)
export HOME="${ARGOS_HOME:-$APP/.argos-home}"
mkdir -p "$HOME"
ARGOSPM="$APP/backend/venv/bin/argospm"
LANGS=("$@")
[ ${#LANGS[@]} -gt 0 ] || LANGS=(ar de es fr it ja ko nl pt ru tr vi zh)
"$ARGOSPM" update
for l in "${LANGS[@]}"; do
  echo "== ${l} -> en"
  "$ARGOSPM" install "translate-${l}_en"
done
"$ARGOSPM" list
