#!/bin/bash
# What is new since the last run on oot2 (penis6), seedds/nxnative's pull requests and cheemu21's kid-with-sword-remake.
# bash scripts/oot_iphone/check_updates.sh   (ALL=1 lists the last 10 of each again). State in .git/oot_watch; oot2 lands in oot2-up, cheemu21's in cheemu21-up.
cd "$(git rev-parse --show-toplevel)" || exit 1
W=.git/oot_watch; mkdir -p "$W"
LOG='%h %ad %an | %s'
branch_news() {
  local name=$1 url=$2 rb=$3 lb=$4 last now
  echo; echo "=== $name"
  if ! git fetch -q "$url" "+$rb:$lb" 2>/dev/null; then echo "(could not fetch $url)"; return; fi
  last=$(cat "$W/$name" 2>/dev/null); now=$(git rev-parse "$lb")
  if [ -n "$ALL" ] || [ -z "$last" ] || ! git cat-file -e "$last" 2>/dev/null; then
    git log --format="$LOG" --date=short -10 "$now" | cut -c1-200
  elif [ "$last" = "$now" ]; then echo "nothing new"
  else
    git log --format="$LOG" --date=short "$last..$now" | cut -c1-200
    local tools; tools=$(git diff --stat "$last" "$now" -- dm/gfx/tools dm/third_party | tail -1)
    [ -n "$tools" ] && echo "  shader tools changed ($tools): taking this means a full shader recompile"
    git diff --quiet "$last" "$now" -- dm/games/0400486024DEC000 || echo "  the Ocarina of Time profile changed: git diff $last $now -- dm/games/0400486024DEC000/game.tsv"
  fi
  echo "$now" > "$W/$name"
}
branch_news oot2 https://git.eden-emu.dev/penis6/nxnative-penis6 oot2 oot2-up
branch_news cheemu21 https://github.com/cheemu21/kid-with-sword-remake kid-with-sword-remake cheemu21-up
echo; echo "=== seedds/nxnative pull requests"
curl -fsS "https://api.github.com/repos/seedds/nxnative/pulls?state=all&sort=created&direction=desc&per_page=60" -o "$W/prs.json" 2>/dev/null \
  || { echo "(could not reach the GitHub API; try again later: it allows 60 requests an hour without a login)"; exit 0; }
python3 - "$W" <<'EOF'
import json, os, sys
w = sys.argv[1]; prs = json.load(open(os.path.join(w, 'prs.json')))
lf = os.path.join(w, 'prs_last'); last = int(open(lf).read()) if os.path.exists(lf) else 0
if os.environ.get('ALL'): last = 0
new = sorted((p for p in prs if p['number'] > last), key=lambda p: p['number'])
if last and not new: print('nothing new')
for p in new[-40:]:
    state = 'merged' if p.get('merged_at') else p['state']
    text = (p['title'] + ' ' + (p.get('body') or '')).lower()
    tag = ' [Ocarina]' if ('ocarina' in text or '0400486024dec000' in text) else ''
    tag += ' [iOS]' if ('iphone' in text or 'ios' in text.split() or 'ipad' in text) else ''
    print(f"#{p['number']} {state:6} {p['user']['login']:18.18} | {p['title'][:150]}{tag}")
if prs: open(lf, 'w').write(str(max(p['number'] for p in prs)))
EOF
