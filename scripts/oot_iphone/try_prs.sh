#!/bin/bash
# try_prs.sh <pr> [<pr> ...]
# Cherry-picks each seedds/nxnative pull request's own commits (not the rest of upstream main) onto the current branch, one PR at a time.
# A conflict only in docs, READMEs or tests keeps this branch's version of those files and goes on. A conflict in code leaves that PR out
# (the branch goes back to where it was before it) and names the files, so the PRs that apply cleanly still go in.
# Needs a clean working tree (commit first). Untracked files are fine.
cd "$(git rev-parse --show-toplevel)" || exit 1
if ! git diff --quiet || ! git diff --cached --quiet; then echo "uncommitted changes: commit them first"; exit 1; fi
url=https://github.com/seedds/nxnative
echo "fetching upstream main..."
git fetch -q "$url" main:refs/up/main || { echo "could not fetch upstream main"; exit 1; }
applied=""; left=""
for n in "$@"; do
  if ! git fetch -q "$url" "pull/$n/head:refs/pr/$n"; then echo "#$n: fetch failed"; left="$left $n"; continue; fi
  commits=$(git rev-list --reverse --no-merges refs/up/main..refs/pr/$n)
  if [ -z "$commits" ]; then echo "#$n: nothing of its own (already in upstream main)"; left="$left $n"; continue; fi
  before=$(git rev-parse HEAD); fail=""
  for c in $commits; do
    git cherry-pick -x "$c" >/dev/null 2>&1 && continue
    files=$(git diff --name-only --diff-filter=U)
    if [ -z "$files" ]; then git cherry-pick --skip >/dev/null 2>&1; continue; fi   # nothing to change: already here
    code=$(printf '%s\n' "$files" | grep -vE '(^docs/|\.md$|/tests/|env_switches\.tsv$|impact_map\.tsv$)')
    if [ -z "$code" ]; then
      printf '%s\n' "$files" | while read -r f; do git checkout --ours -- "$f" && git add -- "$f"; done
      GIT_EDITOR=true git cherry-pick --continue >/dev/null 2>&1 || git cherry-pick --skip >/dev/null 2>&1
      continue
    fi
    fail="$code"; git cherry-pick --abort >/dev/null 2>&1; break
  done
  if [ -n "$fail" ]; then
    git reset -q --hard "$before"
    echo "#$n: left out, conflicts in code:"; printf '%s\n' "$fail" | sed 's/^/    /'
    left="$left $n"
  else
    echo "#$n: applied ($(printf '%s\n' $commits | wc -l | tr -d ' ') commit(s))"; applied="$applied $n"
  fi
done
echo
echo "applied:${applied:- none}"
echo "left out:${left:- none}"
