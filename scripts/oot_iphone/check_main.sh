#!/bin/bash
# check_main.sh <commit> [<commit> ...]
# For each upstream (seedds main) commit: is its code already in this branch, missing but applying cleanly, or in conflict?
# Hand-ported commits have other hashes, so git's own patch matching misses them; this tests the patch itself,
# backwards (already in) and forwards (applies). Docs, notes and tests are left out of the test. Changes nothing.
# Run from the repo: bash scripts/oot_iphone/check_main.sh 12a44e09 6f50de00 ...
cd "$(git rev-parse --show-toplevel)" || exit 1
git fetch -q https://github.com/seedds/nxnative main:refs/up/main 2>/dev/null
for c in "$@"; do
  if ! git cat-file -e "$c^{commit}" 2>/dev/null; then echo "$c not found (fetch upstream main first)"; continue; fi
  subj=$(git log -1 --format=%s "$c" | cut -c1-80)
  p=$(mktemp)
  git format-patch -1 --stdout "$c" -- . ':(exclude)docs/*' ':(exclude)*.md' ':(exclude)*/tests/*' ':(exclude)*.tsv' > "$p"
  if ! grep -q '^diff --git' "$p"; then st="docs/tests only"
  elif git apply --check -R "$p" 2>/dev/null; then st="ALREADY IN"
  elif git apply --check "$p" 2>/dev/null; then st="missing, applies cleanly"
  else
    bad=$(git apply --check "$p" 2>&1 | sed -n 's/^error: patch failed: \([^:]*\):.*/\1/p' | sort -u | tr '\n' ' ')
    st="missing or partly in, conflicts in: ${bad:-?}"
  fi
  echo "$c  $st"
  echo "          $subj"
  rm -f "$p"
done
