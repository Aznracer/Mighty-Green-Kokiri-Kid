# The Mighty Green Kokiri Kid: Ocarina of Time (0400486024DEC000) on iPhone

Branch: penis6's `oot2` (git.eden-emu.dev/penis6/nxnative-penis6) plus the changes below.
Tested on an iPhone with an Apple A20 Pro GPU, iOS 27.1, inside LiveContainer2, handheld. Game: base v131072.

## Changes on top of oot2 (scripts/oot_iphone)
- oot2_port.py: four patches, each skipped if already there:
  - pool patch: storage takeovers note the serials they evict, so the texture pool tables are patched instead of rebuilt (after seedds#1444 a15c041). Kokiri Forest: ~3,000 full table rebuilds (~11 ms each) down to 16.
  - DM_TEX_LAZY: pool walks leave render-target IDs without a host texture until something makes one (from Peak8D's oot-full-build).
  - gather fix: textureGatherOffsets as four gathers (upstream b1d7c70). Removes the dotted rows the upscaler drew.
  - raw ranges: raw global memory lookups reuse their last range (seedds#1464), about 3 ms less GPU per frame.
- lazy_min.py: DM_TEX_LAZY_MIN_KB, so textures smaller than this are always created. With DM_TEX_LAZY=2 alone, small targets (exposure, luminance) read as zero and the screen flashed white.
- dm/games/0400486024DEC000 shader tables: the split's own tables. This NSP's files differ from the profile's (copy them when the build stops at the table check).

## Build
    DM_DYNAMIC_FPS=1 python3 scripts/build_ipa_from_nsp.py build_input --keys <prod.keys> --romfs separate --allow-shader-regressions
If it stops with "split shader tables differ":
    T=build_input/0400486024DEC000_build/shader/pkg.partial/tables
    cp $T/shader_map.tsv $T/shader_facts.tsv $T/shader_pairs.tsv dm/games/0400486024DEC000/
    [ -f $T/pso_pairs.tsv ] && cp $T/pso_pairs.tsv dm/games/0400486024DEC000/
Then build again. Do not set pso_mtl4: without a pipeline pack for the phone's GPU, the device compiles 33,190 pairs in the background and runs slower.

## Documents/env.txt
    DM_PRESENT_SNAP=1
    DM_PRESENT_UPSCALE=off
    DM_RENDER_SCALE=0.6
    DM_NDSR=game
    DM_NVN_RES_LIMIT_MB=6900
    DM_NVN_TEX_MIP_SKIP=256
    DM_NVN_TEX_MIP_LEVELS=2
    DM_TEX_LAZY=2
    DM_TEX_LAZY_MIN_KB=1024
    DM_TEX_RELEASE=1
    DM_OPMODE=0
    DM_GFX_SCALE=2
    DM_NVN_DISPATCH_OVERLAP=0
    DM_FX_DIRECT=0

## What each setting is for
| Setting | Why |
|---|---|
| DM_NVN_RES_LIMIT_MB | Stops the game before GPU memory runs out; without it the phone froze and needed a hard reboot. Since #1482 it measures the residency set (6900 is an estimate; check the log). |
| DM_GFX_SCALE=2 | The game picks its lower graphics tier: 960x540 internal render, 1280x720 output. |
| DM_NVN_DISPATCH_OVERLAP=0 | With the render-target heap (#1453), overlapped compute stalled the CPU on the GPU (about 2,400 waits in a run, frames up to 150 ms); off: about 25. |
| DM_RENDER_SCALE=0.6 | Caps the game's dynamic resolution at 60% (render_scale.py adds seedds#1497 for v131072 next to the dynamic frame step). With the cooler: frame p50 16.4-17.3 ms, 59.8 fps average, GPU 10-15 ms. 0.65 is the most it has room for. |
| DM_NDSR=game | The game's own upscaler. oot2's MetalFX replacement scales the whole texture, so below the game's full size the 3D world was black. |
| DM_PRESENT_UPSCALE=off | Bilinear to the screen instead of a second MetalFX pass: about 1-2 ms of GPU. |
| DM_FX_DIRECT=0 | With seedds#1541, MetalFX wrote the screen's drawable directly, and the GPU waited for the display: GPU 18-25 ms a frame. With 0 it keeps the present pass: 14-17 ms. |
| DM_TEX_LAZY=2 + MIN_KB | Less texture churn in bright areas without the white flashes. |
| Keep the render-target heap on | DM_NVN_POOL_HEAP=0 is faster but brings back white flashes: the game relies on its render targets sharing memory. |

## Results so far (Kokiri Forest)
With DM_RENDER_SCALE=0.6 and DM_NDSR=game, phone on a cooler: 59.8 fps average, frame p50 16.4-17.3 ms, p95 mostly around 20 ms.
Best runs: frame time p50 16.3-17 ms (60 fps) for stretches, 19-29 ms in heavy scenes; submit thread 3-6 ms, GPU 14-24 ms. No crashes, no rows, no flashes once settled.
Open: the GPU is now the limit (heavy scenes and heat). Storage takeovers no longer cost the submit thread (takeover_note0.py, after seedds#1489).
