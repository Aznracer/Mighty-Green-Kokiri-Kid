#!/bin/bash
# check_main2.sh <commit> [<commit> ...]
# Hunk by hunk: how much of an upstream (seedds main) commit is already in this branch, how much would apply, how much conflicts.
# Works in a throwaway worktree under /tmp, so this branch and its files are not touched.
# Run from the repo: bash scripts/oot_iphone/check_main2.sh 12a44e09 6f50de00 ...
cd "$(git rev-parse --show-toplevel)" || exit 1
WT=$(mktemp -d /tmp/cm.XXXX)
git worktree add -q --detach "$WT" HEAD || exit 1
trap 'git worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"' EXIT
rej_hunks() { find "$WT" -name '*.rej' -path "*$1*" -exec grep -c '^@@' {} + 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}'; }
for c in "$@"; do
  git cat-file -e "$c^{commit}" 2>/dev/null || { echo "$c not found"; continue; }
  echo "== $c $(git log -1 --format=%s "$c" | cut -c1-90)"
  P=$(mktemp)
  git format-patch -1 --stdout "$c" -- . ':(exclude)docs/*' ':(exclude)*.md' ':(exclude)*/tests/*' ':(exclude)*.tsv' ':(exclude).github/*' > "$P"
  for f in $(git show --format= --name-only "$c" -- . ':(exclude)docs/*' ':(exclude)*.md' ':(exclude)*/tests/*' ':(exclude)*.tsv' ':(exclude).github/*'); do
    n=$(git show --format= "$c" -- "$f" | grep -c '^@@')
    if [ ! -e "$WT/$f" ]; then echo "   $f: $n hunks, file not in this branch"; continue; fi
    git -C "$WT" checkout -q -- . ; git -C "$WT" clean -fdq
    git -C "$WT" apply -C1 --reject --include="$f" "$P" >/dev/null 2>&1; fwd=$(rej_hunks "$f")
    git -C "$WT" checkout -q -- . ; git -C "$WT" clean -fdq
    git -C "$WT" apply -R -C1 --reject --include="$f" "$P" >/dev/null 2>&1; rev=$(rej_hunks "$f")
    a=$((n-rev)); b=$((n-fwd)); k=$((fwd-a)); [ $k -lt 0 ] && k=0
    echo "   $f: $n hunks: already in $a, would apply $b, conflict $k"
  done
  rm -f "$P"
done
git -C "$WT" checkout -q -- . 2>/dev/null
