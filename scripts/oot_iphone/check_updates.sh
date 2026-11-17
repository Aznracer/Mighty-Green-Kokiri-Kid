#!/bin/bash
# What is new since the last run on the places this port follows:
#   seedds/nxnative main (the base of branch v4) and its pull requests, and every branch of cheemu21's kid-with-sword-remake.
# Run from anywhere inside the repo: bash scripts/oot_iphone/check_updates.sh   (ALL=1 lists the last 10 of each again)
# The last state seen is kept in the repo's git dir (oot_watch); upstream main lands in the branch upstream-main-up,
# cheemu21's branches under refs/oot_watch/cheemu21/<branch>.
cd "$(dirname "$0")" && cd "$(git rev-parse --show-toplevel)" || exit 1   # works from any folder
W=$(git rev-parse --git-common-dir)/oot_watch; mkdir -p "$W" || { echo "cannot write $W"; exit 1; }
LOG='%h %ad %an | %s'
export GIT_TERMINAL_PROMPT=0   # a gone or private repo fails instead of waiting for a password
FETCH="git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 fetch -q --no-tags"

changes_note() {   # old new: what taking these commits means for this build
  local tools; tools=$(git diff --stat "$1" "$2" -- dm/gfx/tools dm/third_party dm/gfx/nvn/dmsh_chain.h | tail -1)
  [ -n "$tools" ] && echo "  shader tools changed ($tools): taking this means a full shader recompile"
  git diff --quiet "$1" "$2" -- dm/games/0400486024DEC000 || echo "  the Ocarina of Time profile changed: git diff $1 $2 -- dm/games/0400486024DEC000"
}

branch_news() {   # name, url, remote branch, local branch
  local name=$1 url=$2 rb=$3 lb=$4 last now err
  echo; echo "=== $name"
  if ! err=$($FETCH "$url" "+refs/heads/$rb:refs/oot_watch/$lb" 2>&1); then
    echo "(could not fetch $url $rb)"; echo "$err" | sed 's/^/  git: /' | head -4; return
  fi
  now=$(git rev-parse "refs/oot_watch/$lb")
  git branch -f "$lb" "$now" >/dev/null 2>&1 || echo "  ($lb is checked out, so only refs/oot_watch/$lb was updated)"
  last=$(cat "$W/$name" 2>/dev/null)
  if [ -n "$ALL" ] || [ -z "$last" ] || ! git cat-file -e "$last" 2>/dev/null; then
    git log --format="$LOG" --date=short -10 "$now" | cut -c1-200
  elif [ "$last" = "$now" ]; then echo "nothing new"
  else
    git log --format="$LOG" --date=short "$last..$now" | cut -c1-200
    changes_note "$last" "$now"
  fi
  echo "$now" > "$W/$name"
}

repo_news() {   # name, url: every branch of the repository, new branches and new commits on old ones
  local name=$1 url=$2 heads st="$W/$name.heads" any=0 sha ref b old
  echo; echo "=== $name (all branches)"
  if ! heads=$(git ls-remote --heads "$url" 2>&1); then
    echo "(could not reach $url)"; echo "$heads" | sed 's/^/  git: /' | head -4; return
  fi
  touch "$st"
  while read -r sha ref; do
    [ -n "$sha" ] || continue
    b=${ref#refs/heads/}
    old=$(awk -v r="$ref" '$2 == r { print $1 }' "$st")
    if [ -z "$ALL" ] && [ "$old" = "$sha" ]; then continue; fi
    any=1
    if ! $FETCH "$url" "+$ref:refs/oot_watch/$name/$b" >/dev/null 2>&1; then echo "  $b: (could not fetch)"; continue; fi
    if [ -z "$old" ]; then
      echo "  new branch: $b"
      git log --format="    $LOG" --date=short -5 "$sha" | cut -c1-200
    elif [ -n "$ALL" ] || ! git cat-file -e "$old" 2>/dev/null; then
      echo "  $b:"
      git log --format="    $LOG" --date=short -10 "$sha" | cut -c1-200
    else
      echo "  $b: new commits"
      git log --format="    $LOG" --date=short "$old..$sha" | cut -c1-200
      changes_note "$old" "$sha" | sed 's/^/  /'
    fi
  done <<< "$heads"
  while read -r old ref; do   # branches that are gone
    [ -n "$ref" ] || continue
    printf '%s\n' "$heads" | awk -v r="$ref" '$2 == r { f = 1 } END { exit !f }' || { echo "  branch gone: ${ref#refs/heads/}"; any=1; }
  done < "$st"
  [ "$any" = 1 ] || echo "nothing new"
  printf '%s\n' "$heads" > "$st"
}

branch_news upstream-main https://github.com/seedds/nxnative.git main upstream-main-up
repo_news cheemu21 https://github.com/cheemu21/kid-with-sword-remake

echo; echo "=== seedds/nxnative pull requests"
curl -fsS "https://api.github.com/repos/seedds/nxnative/pulls?state=all&sort=created&direction=desc&per_page=60" -o "$W/prs.json" 2>/dev/null \
  || { echo "(could not reach the GitHub API; try again later: it allows 60 requests an hour without a login)"; exit 0; }
python3 - "$W" <<'EOF'
import json, os, sys
w = sys.argv[1]; prs = json.load(open(os.path.join(w, 'prs.json')))
lf = os.path.join(w, 'prs_last'); last = int(open(lf).read()) if os.path.exists(lf) else 0
if os.environ.get('ALL'): last = 0
def state(p): return 'merged' if p.get('merged_at') else p['state']
new = sorted((p for p in prs if p['number'] > last), key=lambda p: p['number'])
if last and not new: print('nothing new')
for p in new[-40:]:
    text = (p['title'] + ' ' + (p.get('body') or '')).lower()
    tag = ' [Ocarina]' if ('ocarina' in text or '0400486024dec000' in text) else ''
    tag += ' [iOS]' if ('iphone' in text or 'ios' in text.split() or 'ipad' in text) else ''
    print(f"#{p['number']} {state(p):6} {p['user']['login']:18.18} | {p['title'][:150]}{tag}")
if prs: open(lf, 'w').write(str(max(p['number'] for p in prs)))
# Pull requests this build has taken in before upstream merged them: once one is merged, pull main instead
watch = {2912: 'Mario Kart World CPU cost (merged into v4 by hand)', 2925: 'microphone input (merged into v4 by hand)', 2940: 'Ocarina DM_DRS_LEVEL (merged into v4 by hand)'}
seen = {p['number']: p for p in prs}
print(); print('=== pull requests taken into v4 early')
for n, what in watch.items():
    p = seen.get(n)
    s = state(p) if p else 'not in the last 60 (look on GitHub)'
    print(f"  #{n} {what}: {s}" + ('  -> merged upstream: pull main' if p and p.get('merged_at') else ''))
EOF
