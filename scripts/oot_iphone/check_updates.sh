#!/bin/bash
# What is new since the last run on the three places this port follows:
#   oot2 (penis6, git.eden-emu.dev), seedds/nxnative's pull requests, cheemu21's kid-with-sword-remake.
# Run from anywhere inside the repo: bash scripts/oot_iphone/check_updates.sh   (ALL=1 lists the last 10 of each again)
# The last state seen is kept in the repo's git dir (oot_watch); oot2 lands in the branch oot2-up, cheemu21's in cheemu21-up.
cd "$(dirname "$0")" && cd "$(git rev-parse --show-toplevel)" || exit 1   # works from any folder
W=$(git rev-parse --git-common-dir)/oot_watch; mkdir -p "$W" || { echo "cannot write $W"; exit 1; }
LOG='%h %ad %an | %s'
export GIT_TERMINAL_PROMPT=0   # a gone or private repo fails instead of waiting for a password

branch_news() {   # name, url, remote branch, local branch
  local name=$1 url=$2 rb=$3 lb=$4 last now err
  echo; echo "=== $name"
  # Fetch into a remote-tracking-style ref, so a checked-out oot2-up / cheemu21-up never blocks it.
  if ! err=$(git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 fetch -q --no-tags "$url" "+refs/heads/$rb:refs/oot_watch/$lb" 2>&1); then
    echo "(could not fetch $url $rb)"; echo "$err" | sed 's/^/  git: /' | head -4
    git ls-remote --heads "$url" 2>/dev/null | sed 's#.*refs/heads/#  branch there: #' | head -8
    return
  fi
  now=$(git rev-parse "refs/oot_watch/$lb")
  git branch -f "$lb" "$now" >/dev/null 2>&1 || echo "  ($lb is checked out, so only refs/oot_watch/$lb was updated)"
  last=$(cat "$W/$name" 2>/dev/null)
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

# seedds pull requests this port wants, and whether oot2 has taken them in yet (they do not patch cleanly onto oot2)
if git rev-parse -q --verify refs/oot_watch/oot2-up >/dev/null; then
  echo; echo "=== wanted pull requests already in oot2?"
  has() { git grep -q "$2" refs/oot_watch/oot2-up -- dm && echo "  #$1 $3: yes" || echo "  #$1 $3: no"; }
  has 1473 tex_mtl_raw            "submit thread unretained (CPU; ported in v3)"
  has 1644 pkg_hand_over          "long-session GPU page faults"
  has 1708 MDX_MESH_GRID          "mesh draws split at 1024 workgroups (page faults)"
  has 1721 g_treg_sparse_synced   "texture bindings after sparse mapping changes"
  has 1730 GMEM_RUN_MAX           "contiguous memory-pool runs merged"
  has 1731 DM_NVN_COPY_ABSORB     "texture upgrades, BC targets, retired descriptors"
  has 1752 RawResolveRange        "raw loads resolve their pool once (mesh shaders faster)"
  has 04419bc2 "read one word at a time" "upstream: vector raw loads, occlusion, dynamic resolution (GPU 16.3 -> 12.6 ms)"
  has 1833 shader_raw_direct      "raw memory at Metal GPU addresses (Ocarina)"
fi

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
