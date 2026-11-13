#!/bin/bash
# check_pr.sh <PR number> [...]: for each seedds/nxnative pull request, its description, its files, and hunk by hunk how much of it
# is already in this branch, would apply, or conflicts (all of the PR's commits together, against where it branched from main).
# Works in a throwaway worktree under /tmp; this branch and its files are not touched.
# Run from the repo: bash scripts/oot_iphone/check_pr.sh 2259 2260
cd "$(git rev-parse --show-toplevel)" || exit 1
U=https://github.com/seedds/nxnative
git fetch -q "$U" main:refs/up/main 2>/dev/null
WT=$(mktemp -d /tmp/cp.XXXX)
git worktree add -q --detach "$WT" HEAD || exit 1
trap 'git worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"' EXIT
rej_hunks() { find "$WT" -name '*.rej' -path "*$1*" -exec grep -c '^@@' {} + 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}'; }
X=(':(exclude)docs/*' ':(exclude)*.md' ':(exclude)*/tests/*' ':(exclude)*.tsv' ':(exclude).github/*')
for n in "$@"; do
  git fetch -q "$U" "pull/$n/head:refs/pr/$n" || { echo "== #$n not fetched"; continue; }
  B=$(git merge-base refs/up/main refs/pr/$n)
  echo "================ #$n ($(git rev-list --count $B..refs/pr/$n) commits)"
  curl -fsS "https://api.github.com/repos/seedds/nxnative/pulls/$n" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['title']); print((d['body'] or '')[:1500])" 2>/dev/null
  echo "--- files"; git diff --stat "$B" "refs/pr/$n" | tail -12
  P=$(mktemp); git diff "$B" "refs/pr/$n" -- . "${X[@]}" > "$P"
  for f in $(git diff --name-only "$B" "refs/pr/$n" -- . "${X[@]}"); do
    h=$(git diff "$B" "refs/pr/$n" -- "$f" | grep -c '^@@')
    if [ ! -e "$WT/$f" ]; then echo "   $f: $h hunks, file not in this branch"; continue; fi
    git -C "$WT" checkout -q -- . ; git -C "$WT" clean -fdq
    git -C "$WT" apply -C1 --reject --include="$f" "$P" >/dev/null 2>&1; fwd=$(rej_hunks "$f")
    git -C "$WT" checkout -q -- . ; git -C "$WT" clean -fdq
    git -C "$WT" apply -R -C1 --reject --include="$f" "$P" >/dev/null 2>&1; rev=$(rej_hunks "$f")
    a=$((h-rev)); b=$((h-fwd)); k=$((fwd-a)); [ $k -lt 0 ] && k=0
    echo "   $f: $h hunks: already in $a, would apply $b, conflict $k"
  done
  rm -f "$P"
done
