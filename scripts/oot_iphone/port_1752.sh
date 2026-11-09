#!/bin/bash
# port_1752.sh: seedds/nxnative PR #1752 ("raw global memory loads through one pointer at constant offsets resolve its pool once", plus its
# pool-table search as a loop) on top of oot2's translator. The PR ships translator dlls built on upstream's translator, so they can't be
# copied over oot2's. This applies only its source change (GlobalToStorage.cs) to oot2's in-repo translator source, rebuilds the translator
# with dotnet, puts the new dlls in dmsh_xlate_bin, updates the chain lock and header, and commits all of it on the current branch (v3-prs).
# If the source change doesn't apply cleanly, or the build fails, nothing is changed. The old translator is kept in /tmp/dmsh_xlate_bin.oot2.
# Afterwards the build recompiles every shader (the chain changes).
cd "$(git rev-parse --show-toplevel)" || exit 1
G=dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader/Translation/Optimizations/GlobalToStorage.cs
BIN=dm/gfx/tools/dmsh_xlate_bin
url=https://github.com/seedds/nxnative
[ "$(git branch --show-current)" = "v3-prs" ] || { echo "switch to the v3-prs branch first (git checkout v3-prs)"; exit 1; }
git diff --quiet HEAD -- "$G" "$BIN" dm/gfx/tools/dmsh_chain.lock dm/gfx/nvn/dmsh_chain.h || { echo "the translator files have uncommitted changes: commit or discard them first"; exit 1; }
command -v dotnet >/dev/null || { echo "dotnet not found"; exit 1; }

echo "== fetching #1752 and upstream main"
git fetch -q "$url" main:refs/up/main && git fetch -q "$url" pull/1752/head:refs/pr/1752 || { echo "fetch failed"; exit 1; }
base=$(git merge-base refs/up/main refs/pr/1752)
git diff "$base" refs/pr/1752 -- "$G" > /tmp/pr1752_g2s.patch
[ -s /tmp/pr1752_g2s.patch ] || { echo "the PR has no change to $G"; exit 1; }

echo "== applying the source change to oot2's translator"
if ! git apply -3 /tmp/pr1752_g2s.patch; then
  echo "it does not apply cleanly; conflict regions in GlobalToStorage.cs:"
  grep -n '^<<<<<<<\|^=======\|^>>>>>>>' "$G" | head -30
  git checkout HEAD -- "$G"; echo "nothing changed"; exit 1
fi

echo "== building the translator (dotnet publish)"
out=$(mktemp -d)
if ! dotnet publish dm/gfx/tools/dmsh_xlate/dmsh_xlate.csproj -c Release -o "$out" -nologo -v quiet; then
  echo "the translator build failed (the errors are above)"; git checkout HEAD -- "$G"; echo "nothing changed"; exit 1
fi
rm -rf /tmp/dmsh_xlate_bin.oot2 && cp -R "$BIN" /tmp/dmsh_xlate_bin.oot2
n=0; for f in "$BIN"/*.dll "$BIN"/dmsh_xlate.pdb; do b=$(basename "$f"); [ -f "$out/$b" ] && cp "$out/$b" "$f" && n=$((n+1)); done
echo "   $n files replaced in $BIN (old ones in /tmp/dmsh_xlate_bin.oot2)"
if ! "$BIN/dmsh_xlate" --source-sha >/dev/null 2>&1; then
  echo "the new translator does not run; restoring the old one"; rm -rf "$BIN" && cp -R /tmp/dmsh_xlate_bin.oot2 "$BIN"; git checkout HEAD -- "$G"; exit 1
fi

echo "== updating the chain lock and header"
python3 dm/gfx/tools/tool_lock.py --update-lock && python3 dm/gfx/tools/dmsh_chain.py --header || { echo "lock / header update failed"; exit 1; }
git add -- "$G" "$BIN" dm/gfx/tools/dmsh_chain.lock dm/gfx/nvn/dmsh_chain.h
git commit -q -m "Port seedds/nxnative PR #1752 to oot2's translator: raw loads through one pointer resolve their pool once (rebuilt dmsh_xlate)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01WGrCTWig49u9S8ZCH37TUc"
echo "== done: $(git log --oneline -1)"
grep DMSH_CHAIN dm/gfx/nvn/dmsh_chain.h | tail -1
