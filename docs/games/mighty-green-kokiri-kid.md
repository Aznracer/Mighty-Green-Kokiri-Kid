# Mighty Green Kokiri Kid: Ocarina of Time at 60 fps on iPhone

The Legend of Zelda: Ocarina of Time (Switch 2, title 0400486024DEC000, update v131072, main E0F3CCFAF50065AE4EA01EB5AEB13B1A) built with nxnative for iPhone, tuned for a steady 60 fps at the game's own 3D resolution.

Branch: `mighty-green-kokiri-kid-v3`, on penis6's `oot2` branch (git.eden-emu.dev/penis6/nxnative-penis6, commit f0c0e510) with the patches below.

## Tested on

- **Device:** iPhone Duo (iPhone19,4, A20 Pro GPU, Metal working set 8,192 MB)
- **System:** iOS 27.1, app run inside LiveContainer
- **Cooling:** a TEC (thermoelectric) phone cooler on the back of the phone for every run. Results without a cooler will be worse: heat is what pushes iOS to move the game onto the efficiency cores.
- **Area:** Kokiri Forest from a save, 3 to 6 minutes per run

## Result

About 5.5 minutes in Kokiri Forest at a near-locked 60 fps (frame time p50 16.6 ms, p95 about 18 ms), the 3D scene drawn at 960x540 and upscaled by MetalFX to 1280x720. CPU frame preparation 3 to 4.5 ms, GPU about 14 ms, memory peak 5,728 MB (under the GPU memory guard's 5,810 MB line), heat state 0 almost throughout. Brief dips into the 50s remain in the heaviest scenes, and when iOS moves the game to the efficiency cores (mostly when the phone is warm).

## Build

On a Mac, from the repository root, with the base game NSP, the update and your own keys in `build_input` (none of them are in this repository):

```
git checkout -B mighty-green-kokiri-kid-v3 oot2-up        # oot2 at f0c0e510
python3 scripts/oot_iphone/oot2_port.py      # lazy textures (DM_TEX_LAZY), textureGatherOffsets fix; skips what oot2 already has
python3 scripts/oot_iphone/lazy_min.py       # DM_TEX_LAZY_MIN_KB: small textures are always made (no white flashes)
python3 scripts/oot_iphone/unretained.py     # seedds#1473: the submit thread's texture / encoder lookups return unretained (less CPU)
python3 scripts/oot_iphone/view_nil.py       # seedds#1607 (already in oot2 f0c0e510: prints "already patched")
git diff aa7b860a~1 aa7b860a -- dm/host/hle_thread.c > /tmp/wake.diff    # cheemu21 / Xipzer: guest thread wakes after the lock is let go
patch -p1 --forward --no-backup-if-mismatch < /tmp/wake.diff; rm -f dm/host/hle_thread.c.rej   # 3 of 43 hunks fail on oot2: expected
python3 scripts/oot_iphone/wake_fix.py       # those 3: every unlock of the thread lock goes through g_unlock
DM_DYNAMIC_FPS=1 python3 scripts/build_ipa_from_nsp.py build_input --keys <your prod.keys> --romfs separate --allow-shader-regressions
```

`aa7b860a` comes from cheemu21's kid-with-sword-remake (`git fetch https://github.com/cheemu21/kid-with-sword-remake kid-with-sword-remake`). After the patch, `dm/host/hle_thread.c` should have 51 `g_unlock();`, 4 `wake_flush();`, 7 `sig_pend` and exactly 1 `pthread_mutex_unlock(&G);`.

If the build stops at the shader split check, copy the split's tables into the profile and build again: `cp build_input/0400486024DEC000_build/shader/pkg.partial/tables/*.tsv dm/games/0400486024DEC000/`. Do not set `pso_mtl4` in `game.tsv`: without a pipeline pack for the A20 it prebuilds about 33,000 pipelines in the background and runs worse.

Installing: after a build that recompiled shaders, delete the app, install the new IPA and restore the Documents folder (saves, `env.txt`, `pso_user.tsv`). After a build without a shader recompile, installing over the app is enough. `pso_user.tsv` lists pipelines by the game's shader IDs and stays valid across builds.

## env.txt

```
DM_PRESENT_SNAP=1
DM_PRESENT_UPSCALE=off
DM_RENDER_SCALE=0.75
DM_NDSR=metalfx
DM_NVN_RES_LIMIT_MB=6900
DM_NVN_TEX_MIP_SKIP=1024
DM_NVN_TEX_MIP_LEVELS=1
DM_TEX_LAZY=2
DM_TEX_LAZY_MIN_KB=1024
DM_TEX_RELEASE=1
DM_OPMODE=0
DM_GFX_SCALE=2
DM_NVN_DISPATCH_OVERLAP=0
```

| Setting | What it does here |
|---|---|
| `DM_GFX_SCALE=2` | the game's lighter output tier: 1280x720 output |
| `DM_RENDER_SCALE=0.75` | fixes the 3D views at 0.75 of the output (960x540, the game's usual size) and turns its dynamic resolution off. 0.8 went over the GPU budget (30s to 40s fps) |
| `DM_NDSR=metalfx` | MetalFX's spatial scaler replaces the game's own four-dispatch upscaler: sharper, and no more GPU time than the game's |
| `DM_PRESENT_UPSCALE=off` | the 1280x720 picture is stretched to the screen bilinearly (about 0.2 ms) |
| `DM_NVN_TEX_MIP_SKIP=1024`, `DM_NVN_TEX_MIP_LEVELS=1` | large textures without their finest level: keeps memory under the guard line. 2048 peaked at 5,790 MB and set off the guard's texture reloads (stutter) |
| `DM_NVN_RES_LIMIT_MB=6900` | the GPU memory guard lets go from 5,810 MB and stops the game at 6,900 |
| `DM_TEX_LAZY=2`, `DM_TEX_LAZY_MIN_KB=1024` | no host texture for GPU-only pool IDs until used, except small ones (which read as zero and flashed white) |
| `DM_TEX_RELEASE=1` | releases uploaded textures' guest copies. `2` loses textures after area changes |
| `DM_NVN_DISPATCH_OVERLAP=0` | needed with the render-target placement heap, or the allocator waits on the GPU |
| `DM_PRESENT_SNAP=1`, `DM_OPMODE=0` | present snapshots; handheld mode |

## What did not work (on this phone)

- **`DM_NVN_RT_RECLAIM=1`** (render targets reclaimed): GPU memory allocation reached about 8.5 GB, and runs froze after loading the save, once needing a hard reboot.
- **`DM_PRESENT_UPSCALE=metalfx`** (MetalFX to the screen): looks sharp, but costs 0.7 to 1.3 ms of GPU and raises CPU time, drops to 40 to 50 fps, and white flashes came back. Together with `DM_NDSR=metalfx` it hung the GPU after loading (other apps' widgets crashed too).
- **`DM_FRAME_WG=1`** (Deadline boost, the frame workgroup): about a dozen of the game's threads join it, and frame times went to 47 to 125 ms at p95. cheemu21 turned it off for Ocarina of Time for the same reason. The code is in `frame_wg.py` but not applied in v3.
- **`DM_NVN_GMEM_SKIP=1`** (skip unused pools): the title screen's GPU time went from 24 to 35 ms and the submit thread waited on the GPU (20 to 30 fps).
- **`DM_RENDER_SCALE=0.8`**: GPU 16 to 17.5 ms p50, 20 to 24 ms p95.
- **`DM_QOS_MAP=1`**, **`DM_RT_COMP=15`**, **`pso_mtl4`**: worse or no effect.

## Known limits

- **Efficiency cores:** after a few minutes, especially when the phone warms up, iOS can move the game's threads to the efficiency cores (performance-core share from about 50% down to 0 to 10%). Frame preparation then takes 7 to 10 ms instead of 3 to 4.5, and the frame rate dips into the 40s and 50s. Starting cool, with the cooler on, keeps it on the performance cores. Screen recording also costs frames.
- **Graphics headroom:** at 0.75 the GPU is near its budget. The iPhone's GPU clocks itself to the frame deadline, so its measured time stays near 14 ms until the clock runs out (0.8 crossed that line). Higher quality costs heat first.
- **Single grass blades white for a frame:** oot2 found these with fast and relaxed shader maths (5ab5b107, Mac libraries only). The iPhone libraries are compiled with relaxed maths, so they likely show it too. Safe maths would fix it at some GPU cost (not done).
- **Hyrule Field:** two foliage mesh pipelines fail to link there until seedds#1628 is taken (shader recompile).

## Following upstream

`scripts/oot_iphone/check_updates.sh` lists what is new on oot2, on cheemu21's kid-with-sword-remake and in seedds/nxnative's pull requests since the last run, flags shader-tool changes (a full shader recompile) and Ocarina profile changes, and says whether oot2 has taken the pull requests this branch ports. It runs from any folder.

## Credits

penis6 (oot2), seedds and the nxnative contributors, cheemu21 (kid-with-sword-remake), Xipzer (wake after unlock, frame workgroup).
