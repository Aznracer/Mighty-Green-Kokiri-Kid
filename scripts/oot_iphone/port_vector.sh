#!/bin/bash
# port_vector.sh: upstream's vector raw loads (seedds/nxnative 04419bc2, plus its fix 3376af3 / PR #1813) on top of oot2's translator.
# A 64- or 128-bit raw global load (through the memory pool table) becomes one vector load instead of 2 or 4 separate word loads. Upstream measured
# Ocarina's frame on an M4 Pro: GPU 17.0 -> 13.9 ms from this alone (foliage mesh shaders: 464 of 506 raw words read as 116 such loads).
# oot2's translator has diverged (bind-time pointer sites, PR #1585): vector_loads.patch is upstream's change merged into oot2's sources, with the
# pointer site passed to the vector helper the way oot2 passes it to its scalar raw loads. Only the translator sources change; the occlusion part of
# 04419bc2 is already in oot2.
# Steps: apply the patch, rebuild the translator with dotnet, put the new dlls in dmsh_xlate_bin, update the chain lock and header, commit on v3-vec.
# If the patch doesn't apply, or the build fails, nothing is changed. The old translator is kept in /tmp/dmsh_xlate_bin.oot2.
# Afterwards the IPA build recompiles every shader (the chain changes), and the phone prepares its pipelines again on first launch.
cd "$(git rev-parse --show-toplevel)" || exit 1
HERE=scripts/oot_iphone
PATCH=$HERE/vector_loads.patch
SRC=dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader
BIN=dm/gfx/tools/dmsh_xlate_bin
[ "$(git branch --show-current)" = "v3-vec" ] || { echo "switch to a test branch first: git checkout -b v3-vec"; exit 1; }
[ -s "$PATCH" ] || { echo "missing $PATCH (put vector_loads.patch next to this script)"; exit 1; }
git diff --quiet HEAD -- "$SRC" "$BIN" dm/gfx/tools/dmsh_chain.lock dm/gfx/nvn/dmsh_chain.h || { echo "the translator files have uncommitted changes: commit or discard them first"; exit 1; }
grep -q 'GenerateRawVectorLoad' "$SRC/Translation/Optimizations/GlobalToStorage.cs" && { echo "the translator already has the vector loads (oot2 took them?): nothing to do"; exit 0; }
command -v dotnet >/dev/null || { echo "dotnet not found"; exit 1; }

echo "== applying the vector loads to oot2's translator"
if ! git apply --3way "$PATCH"; then
  echo "it does not apply cleanly (oot2's translator changed since the patch was made); conflict regions:"
  git diff --name-only --diff-filter=U
  git checkout HEAD -- "$SRC"; git reset -q -- "$SRC"; echo "nothing changed"; exit 1
fi

echo "== building the translator (dotnet publish)"
out=$(mktemp -d)
if ! dotnet publish dm/gfx/tools/dmsh_xlate/dmsh_xlate.csproj -c Release -o "$out" -nologo -v quiet; then
  echo "the translator build failed (the errors are above: paste them to Claude)"; git checkout HEAD -- "$SRC"; git reset -q -- "$SRC"; echo "nothing changed"; exit 1
fi
rm -rf /tmp/dmsh_xlate_bin.oot2 && cp -R "$BIN" /tmp/dmsh_xlate_bin.oot2
n=0; for f in "$BIN"/*.dll "$BIN"/dmsh_xlate.pdb; do b=$(basename "$f"); [ -f "$out/$b" ] && cp "$out/$b" "$f" && n=$((n+1)); done
echo "   $n files replaced in $BIN (old ones in /tmp/dmsh_xlate_bin.oot2)"
if ! "$BIN/dmsh_xlate" --source-sha >/dev/null 2>&1; then
  echo "the new translator does not run; restoring the old one"; rm -rf "$BIN" && cp -R /tmp/dmsh_xlate_bin.oot2 "$BIN"; git checkout HEAD -- "$SRC"; git reset -q -- "$SRC"; exit 1
fi

echo "== updating the chain lock and header"
python3 dm/gfx/tools/tool_lock.py --update-lock && python3 dm/gfx/tools/dmsh_chain.py --header || { echo "lock / header update failed"; exit 1; }
git add -- "$SRC" "$BIN" dm/gfx/tools/dmsh_chain.lock dm/gfx/nvn/dmsh_chain.h "$HERE/port_vector.sh" "$PATCH"
git commit -q -m "Port upstream's vector raw loads (04419bc2 + 3376af3 / PR #1813) to oot2's translator: a 64- / 128-bit raw global load is one vector load (rebuilt dmsh_xlate)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01WGrCTWig49u9S8ZCH37TUc"
echo "== done: $(git log --oneline -1)"
grep DMSH_CHAIN dm/gfx/nvn/dmsh_chain.h | tail -1
